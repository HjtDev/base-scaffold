#!/usr/bin/env bash
#
# deploy-prod.sh — push-based production deploy. BASE-DESIGN.md §9.
#
# Rsyncs the current working tree to the target server, then runs the rebuild/rollout
# remotely over SSH: build, start, wait for backend healthy, back up the database,
# migrate, verify every container, reload nginx. Configuration for WHERE to deploy lives
# in deploy/deploy.prod.env (gitignored; deploy.prod.env.example is the tracked template)
# — never in this script.
#
# MIGRATION SAFETY — read this before touching a migration that ships through here:
# the new code starts serving traffic (step: `up -d`) BEFORE migrations run (step:
# `migrate`, gated on the backend reporting healthy). That ordering is deliberate — it's
# what lets a single container run through a deploy instead of taking an outage window —
# but it means there is a real window where the NEW code runs against the OLD schema.
# That's fine for an additive migration and dangerous for a destructive one. The rule:
# make every migration backward-compatible with the previous release's code — add columns
# nullable, deploy, backfill in a follow-up, drop the old column in a LATER release. Never
# rename or drop a column the currently-deployed code still reads or writes.
#
# Usage: deploy/deploy-prod.sh [options]   (see --help)

set -euo pipefail

# ---------------------------------------------------------------------------------------
# setup: locate the repo, parse flags
# ---------------------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
REPO_ROOT="$(dirname -- "${SCRIPT_DIR}")"

usage() {
  cat <<'EOF'
Usage: deploy/deploy-prod.sh [options]

Rsync the current working tree to production and roll it out over SSH:
build, start, wait for the backend to report healthy, back up the database,
run migrate + collectstatic, verify every container, reload nginx.

Options:
  --skip-backup-db   Skip the pre-migration pg_dump backup (NOT recommended —
                      a destructive migration with no backup is unrecoverable)
  --skip-ci-check    Skip verifying GitHub Actions CI is green for this commit
  --follow           Tail `docker compose logs -f` after a successful deploy
  -h, --help         Show this help and exit

Configuration comes from deploy/deploy.prod.env (see
deploy/deploy.prod.env.example): SERVER_HOST, SERVER_USER, SERVER_PATH,
SSH_PORT, SSH_KEY_PATH, HEALTH_TIMEOUT, HEALTH_INTERVAL, SKIP_NGINX_RELOAD.

Must be run from a clean git working tree — there is no override for that
check. This script rsyncs the working tree, not a git ref, so a clean tree
is the only thing that makes "what commit is production running" answerable
after the fact; see DEPLOYED_VERSION on the server.
EOF
}

SKIP_BACKUP_DB=0
SKIP_CI_CHECK=0
FOLLOW=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-backup-db) SKIP_BACKUP_DB=1; shift ;;
    --skip-ci-check) SKIP_CI_CHECK=1; shift ;;
    --follow) FOLLOW=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------------------
# step 1: confirm we're actually at the repo root
# ---------------------------------------------------------------------------------------

if [[ ! -f docker-compose.prod.yml ]]; then
  die "docker-compose.prod.yml not found in ${REPO_ROOT} — run this from inside the repo (deploy/deploy-prod.sh)."
fi

# ---------------------------------------------------------------------------------------
# step 2: validate deploy.prod.env
# ---------------------------------------------------------------------------------------

ENV_FILE="deploy/deploy.prod.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  cat >&2 <<EOF
ERROR: ${ENV_FILE} not found.

Create it from the template and fill in your server details:
  cp deploy/deploy.prod.env.example deploy/deploy.prod.env

Required keys: SERVER_HOST, SERVER_USER, SERVER_PATH
Optional keys: SSH_PORT (default 22), SSH_KEY_PATH, HEALTH_TIMEOUT,
               HEALTH_INTERVAL, SKIP_NGINX_RELOAD
EOF
  exit 1
fi

# shellcheck source=/dev/null   # ENV_FILE is a runtime-configured path, not statically resolvable
source "${ENV_FILE}"

: "${SERVER_HOST:?SERVER_HOST is not set in ${ENV_FILE} — see deploy/deploy.prod.env.example}"
: "${SERVER_USER:?SERVER_USER is not set in ${ENV_FILE} — see deploy/deploy.prod.env.example}"
: "${SERVER_PATH:?SERVER_PATH is not set in ${ENV_FILE} — see deploy/deploy.prod.env.example}"

SSH_PORT="${SSH_PORT:-22}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
SKIP_NGINX_RELOAD="${SKIP_NGINX_RELOAD:-0}"

# ---------------------------------------------------------------------------------------
# step 3: clean working tree — no override, deliberately (see the --help text above)
# ---------------------------------------------------------------------------------------

if [[ -n "$(git status --porcelain)" ]]; then
  {
    echo "ERROR: working tree is not clean — refusing to deploy."
    echo
    echo "This check includes untracked files, not just modified ones: an untracked file"
    echo "gets rsynced to the server exactly like a tracked one, and would otherwise ship"
    echo "with no record of it anywhere. There is no override for this check — this script"
    echo "rsyncs the working tree rather than a git ref, so a clean tree is the only thing"
    echo "that makes \"what commit is production running\" answerable afterwards."
    echo
    git status --short
    echo
    echo "Commit or stash these, then re-run."
  } >&2
  exit 1
fi

DEPLOYED_SHA="$(git rev-parse HEAD)"
DEPLOYED_SHORT="$(git rev-parse --short HEAD)"
DEPLOYED_DESCRIBE="$(git describe --tags --always 2>/dev/null || echo "${DEPLOYED_SHORT}")"

log "Deploying ${DEPLOYED_SHORT} (${DEPLOYED_DESCRIBE}) to ${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}"

# ---------------------------------------------------------------------------------------
# step 4: CI gate (skip with --skip-ci-check)
# ---------------------------------------------------------------------------------------

check_ci() {
  if ! command -v gh >/dev/null 2>&1; then
    log "gh not found — skipping CI check."
    return 0
  fi
  if ! gh auth status >/dev/null 2>&1; then
    log "gh is not authenticated — skipping CI check."
    return 0
  fi
  if ! git remote get-url origin >/dev/null 2>&1; then
    log "no 'origin' remote configured — skipping CI check."
    return 0
  fi

  local run_line status conclusion url
  if ! run_line="$(timeout 30 gh run list --commit "${DEPLOYED_SHA}" --limit 1 \
      --json status,conclusion,url --jq '.[0] | [.status, .conclusion, .url] | @tsv' 2>/dev/null)"; then
    die "gh run list failed or timed out — pass --skip-ci-check to bypass."
  fi

  if [[ -z "${run_line}" ]]; then
    die "No CI run found for commit ${DEPLOYED_SHA} — was it ever pushed? Pass --skip-ci-check to bypass."
  fi

  IFS=$'\t' read -r status conclusion url <<<"${run_line}"
  log "CI run for ${DEPLOYED_SHORT}: ${url}"

  if [[ "${status}" != "completed" ]]; then
    die "CI run is still '${status}' — wait for it, or pass --skip-ci-check."
  fi
  case "${conclusion}" in
    success|skipped) log "CI is green." ;;
    *) die "CI concluded '${conclusion}' for this commit — pass --skip-ci-check to bypass." ;;
  esac
}

if (( SKIP_CI_CHECK )); then
  log "--skip-ci-check passed — not checking CI status."
else
  check_ci
fi

# ---------------------------------------------------------------------------------------
# step 5: SSH preflight + a multiplexed control socket (every later call reuses it)
# ---------------------------------------------------------------------------------------

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deploy-prod.XXXXXX")"
CONTROL_PATH="${WORK_DIR}/ssh-control"

cleanup() {
  ssh -o "ControlPath=${CONTROL_PATH}" -O exit "${SERVER_USER}@${SERVER_HOST}" >/dev/null 2>&1 || true
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

SSH_OPTS=(-p "${SSH_PORT}" -o "ControlMaster=auto" -o "ControlPath=${CONTROL_PATH}" \
          -o "ControlPersist=60s" -o "BatchMode=yes")
if [[ -n "${SSH_KEY_PATH}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY_PATH}")
fi

remote() {
  # shellcheck disable=SC2029   # intentional: callers build the remote command with local
  # (client-side) expansion of our own trusted vars (SERVER_PATH, etc.); anything meant to
  # expand inside the container instead is single-quoted by the caller — see step 10.
  ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" "$@"
}

compose_remote() {
  local cmd="$1"
  remote "cd '${SERVER_PATH}' && docker compose -f docker-compose.prod.yml --env-file .env.prod ${cmd}"
}

log "Checking SSH connectivity..."
if ! remote true; then
  die "Could not connect to ${SERVER_USER}@${SERVER_HOST}:${SSH_PORT}. Check deploy/deploy.prod.env and SSH access."
fi

# ---------------------------------------------------------------------------------------
# step 6: rsync — every exclude from §9 step 2
# ---------------------------------------------------------------------------------------

log "Rsyncing working tree to ${SERVER_PATH}..."
remote "mkdir -p '${SERVER_PATH}'"

RSYNC_RSH="ssh -p ${SSH_PORT} -o ControlPath=${CONTROL_PATH}"
if [[ -n "${SSH_KEY_PATH}" ]]; then
  RSYNC_RSH="${RSYNC_RSH} -i ${SSH_KEY_PATH}"
fi

rsync -az --delete \
  -e "${RSYNC_RSH}" \
  --exclude='.git' \
  --exclude='.idea' \
  --exclude='.vscode' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='media' \
  --exclude='.env' \
  --exclude='.env.prod' \
  --exclude='.env.local' \
  --exclude='deploy/deploy.prod.env' \
  --exclude='.mypy_cache' \
  --exclude='.ruff_cache' \
  --exclude='.pytest_cache' \
  --exclude='staticfiles' \
  --exclude='logs' \
  --exclude='backups' \
  --exclude='*.pyc' \
  ./ "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"

# Record what actually shipped — the payoff for step 3's strict clean-tree check.
DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEPLOYED_BY="$(whoami)@$(hostname)"
printf 'commit: %s\ndescribe: %s\ndeployed_at: %s\ndeployed_by: %s\n' \
  "${DEPLOYED_SHA}" "${DEPLOYED_DESCRIBE}" "${DEPLOYED_AT}" "${DEPLOYED_BY}" \
  | remote "cat > '${SERVER_PATH}/DEPLOYED_VERSION'"

# ---------------------------------------------------------------------------------------
# step 7: confirm required .env.prod files exist on the server
# ---------------------------------------------------------------------------------------

log "Checking required env files on the server..."
MISSING_ENV_FILES=()
for f in ".env.prod" "backend/.env.prod"; do
  if ! remote "test -f '${SERVER_PATH}/${f}'"; then
    MISSING_ENV_FILES+=("${SERVER_PATH}/${f}")
  fi
done

# Note: there is deliberately no frontend/.env.prod — NEXT_PUBLIC_API_URL is a frontend
# build ARG sourced from the root .env.prod, not a runtime env file frontend ever reads.

if (( ${#MISSING_ENV_FILES[@]} > 0 )); then
  {
    echo "ERROR: missing required env file(s) on the server:"
    printf '  - %s\n' "${MISSING_ENV_FILES[@]}"
    echo "Create them on the server (see .env.prod.example / backend/.env.prod.example) before deploying."
  } >&2
  exit 1
fi

# If the analytics profile is active, its secrets must be set. docker-compose.prod.yml
# deliberately reads UMAMI_DB_PASSWORD/UMAMI_APP_SECRET/UMAMI_TWO_FACTOR_ENCRYPTION_KEY
# with an empty (`:-`) default rather than `:?` — compose interpolates every service's
# variables at parse time regardless of which profiles are active, so a `:?` guard there
# would break `docker compose build` for every project that never enables analytics. This
# is the actual enforcement point instead, and it only fires when analytics is on.
ANALYTICS_ENABLED=false
if remote "grep -qE '^COMPOSE_PROFILES=.*analytics' '${SERVER_PATH}/.env.prod'" 2>/dev/null; then
  ANALYTICS_ENABLED=true
  MISSING_UMAMI_KEYS=()
  for key in UMAMI_DB_PASSWORD UMAMI_APP_SECRET UMAMI_TWO_FACTOR_ENCRYPTION_KEY; do
    if ! remote "grep -qE '^${key}=.+' '${SERVER_PATH}/.env.prod'"; then
      MISSING_UMAMI_KEYS+=("${key}")
    fi
  done
  if (( ${#MISSING_UMAMI_KEYS[@]} > 0 )); then
    {
      echo "ERROR: COMPOSE_PROFILES=analytics is set in .env.prod, but the following required key(s) are empty:"
      printf '  - %s\n' "${MISSING_UMAMI_KEYS[@]}"
      echo "Set them in .env.prod (see .env.prod.example's analytics section for generate commands) before deploying."
    } >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------------------
# step 8: build + start
# ---------------------------------------------------------------------------------------

log "Building images on the server..."
compose_remote "build --pull"

log "Starting the stack..."
compose_remote "up -d --remove-orphans"

# ---------------------------------------------------------------------------------------
# step 9: wait for backend healthy — bounded, dumps logs on failure
# ---------------------------------------------------------------------------------------

BACKEND_CID="$(compose_remote "ps -q backend")"
if [[ -z "${BACKEND_CID}" ]]; then
  die "backend container did not start (docker compose ps -q backend returned nothing)."
fi

log "Waiting for backend to report healthy (timeout ${HEALTH_TIMEOUT}s)..."
ELAPSED=0
HEALTH_STATUS="starting"
while (( ELAPSED < HEALTH_TIMEOUT )); do
  HEALTH_STATUS="$(remote "docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' ${BACKEND_CID}" 2>/dev/null || echo "unknown")"
  [[ "${HEALTH_STATUS}" == "healthy" ]] && break
  [[ "${HEALTH_STATUS}" == "unhealthy" ]] && break
  sleep "${HEALTH_INTERVAL}"
  ELAPSED=$(( ELAPSED + HEALTH_INTERVAL ))
done

if [[ "${HEALTH_STATUS}" != "healthy" ]]; then
  {
    echo "ERROR: backend did not become healthy within ${HEALTH_TIMEOUT}s (last status: ${HEALTH_STATUS})"
    echo "---- last 100 lines of backend logs ----"
  } >&2
  compose_remote "logs --tail 100 backend" >&2 || true
  die "Health gate failed — aborting before running migrations."
fi
log "backend is healthy (${ELAPSED}s)."

# ---------------------------------------------------------------------------------------
# step 10: back up the database — unconditional unless --skip-backup-db, and BEFORE
# migrate. This runs inside the backend container (Dockerfile.prod installs
# postgresql-client specifically for this); gzip runs on the server host, since the
# runtime image's contents aren't guaranteed beyond libpq5/postgresql-client/curl.
# ---------------------------------------------------------------------------------------

if (( SKIP_BACKUP_DB )); then
  warn "--skip-backup-db passed — deploying without a pre-migration backup."
else
  # Dump and gzip as two separate remote commands rather than one piped command. A pipe
  # inside the string handed to remote() runs entirely in the REMOTE login shell, which
  # this script's own `set -o pipefail` does not reach and which may not even support
  # pipefail (dash doesn't) — pg_dump failing (bad password, unreachable DB) could leave
  # gzip to exit 0 on an empty stream, and the deploy would proceed as if backed up. Two
  # discrete commands make pg_dump's own exit status the thing `set -e` reacts to.
  BACKUP_BASENAME="pre-migrate-$(date -u +%Y%m%dT%H%M%SZ).sql"
  remote "mkdir -p '${SERVER_PATH}/backups'"
  log "Backing up the database to backups/${BACKUP_BASENAME}.gz..."

  # shellcheck disable=SC2016   # single-quoted on purpose: these $VARS expand inside the
  # CONTAINER's own shell (from backend/.env.prod), not on the server or here.
  PG_DUMP_INNER='PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

  remote "cd '${SERVER_PATH}' && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend sh -c '${PG_DUMP_INNER}' > 'backups/${BACKUP_BASENAME}'"
  remote "cd '${SERVER_PATH}' && gzip -9 'backups/${BACKUP_BASENAME}'"
  BACKUP_NAME="${BACKUP_BASENAME}.gz"
fi

# ---------------------------------------------------------------------------------------
# step 11: migrate + collectstatic — only now, after the health gate, never on boot
# ---------------------------------------------------------------------------------------

log "Running migrations..."
compose_remote "exec -T backend python manage.py migrate --noinput"

log "Collecting static files..."
compose_remote "exec -T backend python manage.py collectstatic --noinput"

# ---------------------------------------------------------------------------------------
# step 12: verify every expected container is running AND healthy
# ---------------------------------------------------------------------------------------

log "Verifying every service is running and healthy..."
SERVICES="$(compose_remote "config --services")"
if [[ -z "${SERVICES}" ]]; then
  die "docker compose config --services returned nothing — cannot verify the deploy."
fi

FAILED_SERVICES=0
while IFS= read -r service; do
  [[ -z "${service}" ]] && continue
  cid="$(compose_remote "ps -q ${service}")"
  if [[ -z "${cid}" ]]; then
    echo "ERROR: ${service} has no running container." >&2
    FAILED_SERVICES=$(( FAILED_SERVICES + 1 ))
    continue
  fi
  state_health="$(remote "docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' ${cid}")"
  state="${state_health%% *}"
  health="${state_health#* }"
  if [[ "${state}" != "running" ]] || { [[ "${health}" != "healthy" ]] && [[ "${health}" != "none" ]]; }; then
    {
      echo "ERROR: ${service} is state='${state}' health='${health}'."
      echo "---- last 100 lines of ${service} logs ----"
    } >&2
    compose_remote "logs --tail 100 ${service}" >&2 || true
    FAILED_SERVICES=$(( FAILED_SERVICES + 1 ))
  else
    log "  ${service}: ${state}/${health}"
  fi
done <<<"${SERVICES}"

if (( FAILED_SERVICES > 0 )); then
  die "${FAILED_SERVICES} service(s) failed verification — see logs above."
fi
log "All services running and healthy."

# ---------------------------------------------------------------------------------------
# step 13: reload nginx, only if nginx -t passes. nginx is host-level, not a compose
# service — both published ports bind 127.0.0.1 and nginx fronts the public traffic.
# ---------------------------------------------------------------------------------------

if [[ "${SKIP_NGINX_RELOAD}" == "1" ]]; then
  log "SKIP_NGINX_RELOAD=1 — skipping nginx reload."
elif remote "command -v nginx >/dev/null 2>&1"; then
  log "Testing nginx configuration..."
  if remote "sudo nginx -t"; then
    log "Reloading nginx..."
    remote "sudo systemctl reload nginx"
  else
    die "nginx -t failed on the server — NOT reloading. Fix the config, then reload manually."
  fi
else
  log "nginx not found on the server — skipping reload."
fi

# ---------------------------------------------------------------------------------------
# summary + optional log follow
# ---------------------------------------------------------------------------------------

log "Deploy complete."
log "  commit: ${DEPLOYED_SHORT} (${DEPLOYED_DESCRIBE})"
log "  server: ${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}"
if (( ! SKIP_BACKUP_DB )); then
  log "  backup: backups/${BACKUP_NAME}"
fi
if [[ "${ANALYTICS_ENABLED}" == "true" ]]; then
  warn "Analytics is enabled. If this is the first deploy with it on, log into Umami now and change the admin password (default admin/umami) before the analytics.<domain> DNS record goes public."
fi

if (( FOLLOW )); then
  log "Following logs (Ctrl+C to stop — the deploy already completed successfully)..."
  ssh -t "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" \
    "cd '${SERVER_PATH}' && docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"
fi
