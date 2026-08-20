#!/usr/bin/env bash
#
# rename-project.sh — replaces the placeholder project name across every tracked file that
# actually contains it, and renders the host-project CLAUDE.md from CLAUDE.md.template.
# BASE-DESIGN.md §11.1, §10.1.
#
# Run once, right after detaching from the scaffold's git history (README.md step 2, before
# this script) and before installing dependencies (step 5, after). Idempotent: re-running with
# the same name is a no-op; re-running with a different name renames again.
#
# The file list is DERIVED by searching the working tree for the current placeholder, not
# hardcoded — a hardcoded list is exactly how docs/BASE-DESIGN.md §11.1 drifted out of sync
# with the repo (see docs/CORRECTIONS.md). Lockfiles (backend/uv.lock,
# frontend/package-lock.json) get a narrow, line-anchored substitution of only the root
# package's own `name` field — never a blind find-and-replace, which could corrupt a dependency
# whose own name happens to contain the placeholder.
#
# This repo's own root CLAUDE.md is base-scaffold's authoring instructions, not a host
# project's, and is never overwritten by this script — see the CLAUDE.md render step below for
# the guard that enforces that.
#
# Usage: scripts/rename-project.sh <new-name> [--dry-run]

set -euo pipefail

# ---------------------------------------------------------------------------------------
# setup: locate the repo, parse flags
# ---------------------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
REPO_ROOT="$(dirname -- "${SCRIPT_DIR}")"

usage() {
  cat <<'EOF'
Usage: scripts/rename-project.sh <new-name> [options]

Replaces the placeholder project name across every file that contains it —
.env.example, .env.prod.example, backend/.env.example, backend/pyproject.toml,
backend/uv.lock, frontend/package.json, frontend/package-lock.json,
frontend/app/layout.tsx — and renders CLAUDE.md.template's host-project
variant into CLAUDE.md.

<new-name> must be a valid Python package name, npm package name, and Docker
container-name prefix all at once: lowercase letters, digits and single
hyphens, starting with a letter (e.g. "my-client-project").

Options:
  --dry-run    Print every planned change without touching any file
  -h, --help   Show this help and exit

Safe to run more than once: a run with the same name that's already active is
a no-op, and CLAUDE.md is only ever rendered once (see the render step).
EOF
}

DRY_RUN=0
NEW_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$NEW_NAME" ]]; then
        echo "Unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      NEW_NAME="$1"
      shift
      ;;
  esac
done

log() { printf '==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [[ -z "$NEW_NAME" ]]; then
  usage >&2
  die "missing <new-name> argument"
fi

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------------------
# step 1: confirm we're at the repo root, validate the new name
# ---------------------------------------------------------------------------------------

[[ -f .env.example ]] || die ".env.example not found in ${REPO_ROOT} — run this from inside the repo (scripts/rename-project.sh)."

# Simultaneously a valid Python package name (backend/pyproject.toml), a valid npm package
# name component (frontend/package.json), and a safe Docker container-name prefix
# (${PROJECT_NAME}_backend etc., docker-compose*.yml) — lowercase letters/digits, single
# hyphens, no leading digit or hyphen, no trailing or doubled hyphen.
if [[ ! "$NEW_NAME" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]]; then
  die "invalid project name '${NEW_NAME}': must be lowercase letters, digits and single hyphens, starting with a letter (e.g. 'my-client-project')."
fi

# ---------------------------------------------------------------------------------------
# step 2: determine the current placeholder name (not hardcoded — read from .env.example,
# so a second rename works from whatever the first rename left behind)
# ---------------------------------------------------------------------------------------

OLD_NAME="$(sed -n 's/^PROJECT_NAME=//p' .env.example | head -n1)"
[[ -n "$OLD_NAME" ]] || die "couldn't read PROJECT_NAME= from .env.example"

if [[ "$OLD_NAME" == "$NEW_NAME" ]]; then
  log "Already named '${NEW_NAME}' — nothing to rename."
else
  log "Renaming '${OLD_NAME}' -> '${NEW_NAME}'$( [[ $DRY_RUN -eq 1 ]] && printf ' (dry run)' )"

  # -------------------------------------------------------------------------------------
  # step 3: derive the file list — search the working tree, not a hardcoded list.
  # Excluded: docs/** and CLAUDE.md (they document the placeholder mechanism, they aren't
  # the value), build/tooling caches, and every REAL .env file (.env, .env.local, .env.prod,
  # deploy/deploy.prod.env — gitignored, project-owned, never touched by this script; only
  # the tracked *.example templates are in scope).
  #
  # Uses `find -prune` rather than grep's own --exclude-dir/--exclude: `grep` isn't
  # guaranteed to be GNU grep (this repo's own dev machine aliases it to ugrep, whose
  # --exclude-dir and hidden-file handling behave differently) — find's -prune is the
  # portable way to do this, then grep -l is only ever run per-file.
  # -------------------------------------------------------------------------------------

  mapfile -t CANDIDATE_FILES < <(
    find . \
      \( -path './.git' -o -path './docs' -o -path './scripts' -o -path './.idea' \
         -o -name node_modules -o -name .venv -o -name .next \
         -o -name __pycache__ -o -name .mypy_cache -o -name .ruff_cache \
         -o -name .pytest_cache \
      \) -prune -o \
      -type f \
      ! -name '.env' ! -name '.env.local' ! -name '.env.prod' ! -name 'deploy.prod.env' \
      -print0 \
    | xargs -0 -r grep -lF -- "$OLD_NAME" 2>/dev/null \
    | sed 's#^\./##' \
    | grep -vx 'CLAUDE.md' \
    | sort
  )

  if [[ ${#CANDIDATE_FILES[@]} -eq 0 ]]; then
    warn "no file outside docs/ contains '${OLD_NAME}' — nothing to substitute."
  fi

  edit_file() {
    # $1 = file  $2 = sed program
    local file="$1" prog="$2"
    if [[ $DRY_RUN -eq 1 ]]; then
      log "  would edit ${file}:"
      grep -nF -- "$OLD_NAME" "$file" | sed 's/^/      /'
    else
      sed -i "$prog" "$file"
      log "  edited ${file}"
    fi
  }

  for f in "${CANDIDATE_FILES[@]}"; do
    case "$f" in
      backend/uv.lock)
        # Line-anchored to the root package's own `name = "..."` line under
        # `source = { virtual = "." }` — a dependency's own name is always written as an
        # inline `{ name = "..." }` and can never match this anchored pattern.
        edit_file "$f" "s/^name = \"${OLD_NAME}\"\$/name = \"${NEW_NAME}\"/"
        ;;
      backend/pyproject.toml)
        edit_file "$f" "s/^name = \"${OLD_NAME}\"\$/name = \"${NEW_NAME}\"/"
        ;;
      frontend/package.json)
        edit_file "$f" "s/\"name\": \"${OLD_NAME}-frontend\"/\"name\": \"${NEW_NAME}-frontend\"/"
        ;;
      frontend/package-lock.json)
        # Two occurrences — the top-level `name` and `packages[""].name` — both are the
        # root package's own name and both take the same substitution.
        edit_file "$f" "s/\"name\": \"${OLD_NAME}-frontend\"/\"name\": \"${NEW_NAME}-frontend\"/g"
        ;;
      frontend/app/layout.tsx)
        edit_file "$f" "s/title: \"${OLD_NAME}\",/title: \"${NEW_NAME}\",/"
        log "  ACTION: frontend/app/layout.tsx's browser-tab title is now '${NEW_NAME}' — that's a slug, not a product name. Replace it with something a user should actually see."
        ;;
      *)
        # .env.example, .env.prod.example, backend/.env.example: whole-word substitution.
        edit_file "$f" "s/\b${OLD_NAME}\b/${NEW_NAME}/g"
        ;;
    esac
  done

  # -------------------------------------------------------------------------------------
  # step 4: post-condition — a rename that silently misses a file is how two projects end
  # up sharing a PROJECT_NAME and colliding container names. Fail loudly if one survives.
  # -------------------------------------------------------------------------------------

  if [[ $DRY_RUN -eq 0 ]]; then
    SURVIVORS=()
    for f in "${CANDIDATE_FILES[@]}"; do
      if grep -qF -- "$OLD_NAME" "$f" 2>/dev/null; then
        SURVIVORS+=("$f")
      fi
    done
    if [[ ${#SURVIVORS[@]} -gt 0 ]]; then
      die "rename incomplete — '${OLD_NAME}' still present in: ${SURVIVORS[*]}"
    fi
    log "Post-condition check passed: '${OLD_NAME}' no longer appears in any renamed file."
  fi
fi

# ---------------------------------------------------------------------------------------
# step 5: render CLAUDE.md from CLAUDE.md.template's host-project variant (§10.1).
#
# Guarded on TWO independent conditions, both required:
#   (a) CLAUDE.md still carries the scaffold's own marker heading — once a project's
#       CLAUDE.md has been rendered (or hand-edited), a re-run must not clobber it.
#   (b) the repo has zero commits — a truly fresh, just-detached clone (README step 2:
#       `rm -rf .git && git init`, before this script) has no commits until step 10. A repo
#       WITH commits is either base-scaffold's own dev repo or a clone that was never
#       detached — either way, overwriting its CLAUDE.md would destroy real authoring
#       history, so this script leaves it alone and says why.
# A clone before detaching is byte-for-byte identical to base-scaffold's own repo (marker
# heading and all) — condition (b) is what tells the two apart, since only base-scaffold's
# real dev history (or an undetached clone) has commits at this point.
# -------------------------------------------------------------------------------------

MARKER='# CLAUDE.md — base-scaffold (the template itself)'
CLAUDE_MD_HAS_MARKER=0
if [[ -f CLAUDE.md ]] && head -n1 CLAUDE.md | grep -qxF "$MARKER"; then
  CLAUDE_MD_HAS_MARKER=1
fi

REPO_HAS_COMMITS=0
if git -C "$REPO_ROOT" rev-parse --verify -q HEAD >/dev/null 2>&1; then
  REPO_HAS_COMMITS=1
fi

if [[ $CLAUDE_MD_HAS_MARKER -eq 0 ]]; then
  log "CLAUDE.md already renders as a host project's (no scaffold marker heading) — leaving it alone."
elif [[ $REPO_HAS_COMMITS -eq 1 ]]; then
  warn "CLAUDE.md still has the scaffold's marker heading, but this repo has git history — leaving it alone."
  note "If this is base-scaffold's own dev repo, that's correct: nothing to do."
  note "If you meant to start a new project, detach first: rm -rf .git && git init (README.md step 2), then re-run this script."
else
  [[ -f CLAUDE.md.template ]] || die "CLAUDE.md.template not found — can't render CLAUDE.md."

  SCAFFOLD_VERSION="$(git -C "$REPO_ROOT" describe --tags --always 2>/dev/null || true)"
  [[ -n "$SCAFFOLD_VERSION" ]] || SCAFFOLD_VERSION="unknown"

  RENDERED="$(
    awk '
      /^# CLAUDE\.md — \{\{PROJECT_NAME\}\}$/ { capture = 1 }
      capture && /^---$/ { exit }
      capture { print }
    ' CLAUDE.md.template \
    | sed -e "s/{{PROJECT_NAME}}/${NEW_NAME}/g" \
          -e "s#{{SCAFFOLD_VERSION}}#${SCAFFOLD_VERSION}#g"
  )"

  [[ -n "$RENDERED" ]] || die "rendering CLAUDE.md.template produced no output — check its host-project variant markers."

  if [[ $DRY_RUN -eq 1 ]]; then
    log "Would render CLAUDE.md from CLAUDE.md.template's host variant ($(printf '%s\n' "$RENDERED" | wc -l) lines, project name '${NEW_NAME}', scaffold version '${SCAFFOLD_VERSION}')."
  else
    printf '%s\n' "$RENDERED" > CLAUDE.md
    log "Rendered CLAUDE.md from CLAUDE.md.template (project name '${NEW_NAME}', scaffold version '${SCAFFOLD_VERSION}')."
    if grep -qF '{{' CLAUDE.md; then
      note "Some placeholders were left as {{...}} on purpose — {{ORG}}, {{APP_REGISTRY_URL}}, and the {{e.g. ...}} illustrative rows — fill those in by hand."
    fi
  fi
fi

log "Done."
