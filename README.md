# base-scaffold

Django 6 (ASGI) + Next.js App Router monorepo starter. Clone it, name it, and it's yours —
`docs/BASE-DESIGN.md` §10. This README is enough to work productively in a cloned project
without reading the design docs first; it's read once on day one and grepped after that.

## What this is

A one-time starter kit, not a living upstream dependency: a project clones this repo, deletes
`.git`, and owns the result from that moment on. There's no `git pull` back to this template —
if the scaffold improves later, that's backported by hand if wanted, never automatic.

**Two categories of code**, not three:

| Category | What it is | Editable? |
|---|---|---|
| **Project code** (`backend/`, `frontend/`, everything here plus everything written later) | Yours from the moment `.git` is deleted | Freely editable, always |
| **Installed backend app packages** (`backend/.venv/…/site-packages`, via `uv`) | Versioned, third-party, reusable Django apps | Never edited directly |
| **Installed frontend app packages** (`frontend/node_modules`, via `npm`) | The same apps' TypeScript/React half | Never edited directly |

If something about an installed app needs to change — settings, URL mounting, a different
view, a different template — the fix goes in `backend/config/`, `backend/core/`, or
`backend/templates/`, never inside the installed package itself. Full rules and the table of
"problem → where the fix goes" are in `docs/INTEGRATION-GUIDE.md` §1.

## Quick start

```bash
# 1. Clone the scaffold — frontend/ and backend/ come together, already wired
git clone https://github.com/yourorg/base-scaffold.git my-client-project
cd my-client-project

# 2. Detach from the scaffold's history — from here on, this is just your code
rm -rf .git && git init

# 3. Name the project (drives container names, DB name, and CLAUDE.md's header)
./scripts/rename-project.sh my-client-project     # see docs/BASE-DESIGN.md §11

# 4. Link the shared design docs (optional, recommended) — docs/APP-DESIGN.md,
# docs/BASE-DESIGN.md, docs/INTEGRATION-GUIDE.md, docs/CLAUDE-CODE-GUIDE-APP.md, and
# docs/CLAUDE-CODE-GUIDE-BASE.md aren't tracked in this repo at all; they're symlinked from a
# sibling clone of the shared docs repo instead of copy-pasted. Skip this and those five paths
# simply don't exist yet — nothing else below depends on them, but CLAUDE.md does once you
# start installing app packages.
cd .. && git clone https://github.com/yourorg/ecosystem-docs.git && cd my-client-project
make docs-link

# 5. Environment
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
python3 -c "import secrets; print(secrets.token_urlsafe(64))"                              # SECRET_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # FERNET_KEY
# stdlib only — cryptography isn't installed until step 6, and its own Fernet.generate_key()
# output is byte-for-byte the same shape as this (32 random bytes, urlsafe-base64), so either
# is a valid key; this form just works before `uv sync` has run.
# paste both into backend/.env, then fill in the DB creds below them.
# (PROJECT_NAME lives in the root .env, not backend/.env — step 3 already set it there.)

# 6. Python + Node dependencies
# `uv sync` pulls hjtdev-appkit (app package #1, a dependency of this scaffold from day
# one) from PyPI, and `npm ci` pulls @hjtdev/appkit from npm — both public registries,
# no credential needed for either half.
cd backend && uv sync --locked && cd ..    # --locked proves pyproject.toml and uv.lock agree
cd frontend && npm ci && cd ..

# 7. Hooks
uv run --directory backend pre-commit install

# 8. Bring the stack up
docker compose up --build

# 9. First superuser
docker compose exec backend python manage.py createsuperuser

# 10. Sanity check — visit each in a browser (`open` is macOS-only; Linux: `xdg-open`)
http://localhost:8000/healthz/            # 200
http://localhost:8000/api/schema/swagger-ui/
http://localhost:3000

# 11. Commit — a fresh clone has no tags yet (step 2 deleted .git), so there's no real
# version to put in place of vX.Y.Z; either drop that part or fill in the scaffold
# version/commit you actually cloned from.
git add . && git commit -m "chore: initial commit from base-scaffold"
```

Step 4 is `make docs-link` (run it again any time; it's idempotent — see `ecosystem-docs`'s own
README for the pattern). Steps 6–7 are `make install`; step 8 is `make up`; `make check` is the
definition of done from here on (`docs/BASE-DESIGN.md` §10.2) — the explicit steps above are
what those targets actually run, spelled out once for a first read.

At this point the project is fully independent. Installing a reusable app package (both
halves) follows the protocol below and in `docs/INTEGRATION-GUIDE.md` §2, and there's no
further contact with the base-scaffold repo unless you're deliberately backporting an
improvement by hand.

## Make targets

| Target | What it does |
|---|---|
| `help` | List all targets (default when you run bare `make`) |
| `install` | `uv sync --locked` + `npm ci` + install pre-commit hooks |
| `up` | Start the dev stack (`docker compose up --build`) |
| `down` | Stop **and remove** the dev stack's containers/network |
| `stop` | Stop the dev stack in place — containers/volumes survive; `make up` resumes them |
| `ps` | Show dev stack container status, including the health column |
| `logs` | Tail all container logs |
| `shell` | Django `shell_plus` in the backend container |
| `migrate` | Apply migrations |
| `migrations` | Create migrations |
| `superuser` | Create a Django superuser |
| `backup` | `pg_dump` the dev database to `backups/<PROJECT_NAME>-<timestamp>.sql.gz` (gitignored) |
| `restore` | `make restore FILE=<path>` — drop and reload the dev database from a backup, confirms first |
| `analytics` | Start the dev stack + optional Umami analytics (`--profile analytics`) — see below |
| `lint` | Ruff + ESLint + format checks — the CI gate |
| `fmt` | Fix everything `lint` checks for — not run by `check` |
| `typecheck` | mypy + `tsc --noEmit` |
| `django-checks` | `makemigrations --check` + `check --deploy`, under a prod-shaped env |
| `test` | Full suite (pytest + vitest) against an ephemeral Postgres + Redis — CI parity |
| `test-fast` | Backend only, skips slow tests — the inner-loop version, not what `check` runs |
| `build` | Production frontend build — proves the Next.js build itself still succeeds |
| `check` | Everything CI gates on, locally — the definition of done |
| `deploy` | Deploy to production (`make deploy ARGS=--follow` to pass flags through) |

## Installing an app package

Most apps have both a backend and a frontend half — install both, don't stop after the
backend just because that's the half that makes the server run. Full protocol, in order,
in `docs/INTEGRATION-GUIDE.md` §2; the shape:

```bash
# backend half — every app package in this ecosystem publishes to PyPI
cd backend
uv add "notifications-app>=1.4,<2.0"

# frontend half, at a matching version — a mismatched pair is the #1 cause of
# "the hook returns undefined for a field the API clearly sends"
cd ../frontend
npm install @yourorg/notifications-app@1.4.2
```

Pinning an unreleased commit instead of a tagged release needs the git+subdirectory form
(backend) or a verified `github:org/pkg#vX:frontend` install (frontend, which has the same
tag/subdirectory-dropping failure mode `appkit` itself hit at v1.0.0 — verify with `npm ls`
before trusting it) — see `docs/INTEGRATION-GUIDE.md` §2 for both fallbacks.

Then: copy the config block from the app's own `README.md` into `backend/config/settings.py`
verbatim, add its `.env` keys, mount its URLs, add it to the `banned-api` ruff table, mount
its frontend provider in `frontend/app/providers.tsx`, and **rebuild, don't just restart** —
`docker compose up --build`. Installing or upgrading changes `uv.lock`/`package-lock.json`,
which changes what's baked into the image; a restart without a rebuild is the single most
common reason "I installed the package but it's not there."

## Where code goes

| Path | Purpose |
|---|---|
| `backend/config/` | Settings, URL routing, ASGI/WSGI, Celery app — project-owned wiring |
| `backend/core/` | The mediator layer: `signals.py`, `services/`, `views/` — the *only* place allowed to import more than one installed app package at once |
| `backend/tools/` | Host-owned helpers for `config/`/`core/`, never importable by an app package — `crypto.py` only; caching/error-envelope/request-ID helpers moved to `appkit` |
| `backend/templates/` | Override point for an installed app's templates |
| `frontend/lib/` | `api-client.ts` — the host's `HttpClient` implementation every installed SDK plugs into via `@hjtdev/appkit`'s `ApiClientProvider` |
| `frontend/app/` | Pages/components — where cross-app UI composition happens |

## Environment

Five `.env` files, each with a tracked `.example`:

| File | Scope | Gitignored? |
|---|---|---|
| `.env` | Compose-level interpolation only — `PROJECT_NAME`, host ports | Yes |
| `.env.prod` | Same scope, production values — lives only on the server, never synced | Yes |
| `backend/.env` | Django dev settings, DB creds, Redis URL, app package keys | Yes |
| `backend/.env.prod` | Same keys, production values — server only | Yes |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` and friends | Yes |

`deploy/deploy.prod.env` (server connection details for `deploy-prod.sh`) is also gitignored;
`deploy/deploy.prod.env.example` is the tracked template. Every `*.example` file is tracked.

## Tests & CI

- `make test` — pytest + vitest against an ephemeral Postgres/Redis stack (`docker-compose.test.yml`), the same thing CI runs.
- `make test-fast` — backend only, skips `slow`-marked tests; the inner dev loop, not what `check` runs.
- `make check` — parity with `.github/workflows/ci.yml`: every CI job/step maps to a target, or is named as a deliberate exclusion in the Makefile's own header comment. Currently excluded: `docker-build` (a minutes-long BuildKit run — `make up`/`make deploy` already exercise the same Dockerfiles) and `security-audit` (a network CVE lookup, advisory-only in CI).
- Tests always run against real Postgres — never SQLite, including in CI.

## Analytics (optional)

The scaffold can run a self-hosted [Umami](https://umami.is) instance behind a compose
profile — **off by default**, so a project that doesn't pay for analytics carries no extra
containers and no script tag. `make up` never starts it, and with
`NEXT_PUBLIC_UMAMI_WEBSITE_ID` unset the frontend renders no script tag at all.

```bash
cp .env.example .env    # if you haven't already — this is where the Umami keys live
make analytics           # docker compose --profile analytics up --build
```

Open `http://localhost:3001`, log in with the default `admin`/`umami` credentials, **change
the password immediately**, register a site, and paste the Website ID into
`NEXT_PUBLIC_UMAMI_WEBSITE_ID`. Full setup, the env keys, the build-time-only rebuild caveat
for `NEXT_PUBLIC_UMAMI_*`, the nginx block, and the security/privacy notes are all in
`docs/UMAMI-ANALYTICS.md`.

## Deployment

```bash
make deploy                    # runs deploy/deploy-prod.sh
make deploy ARGS=--follow      # tail logs after a successful deploy
```

Push-based: rsyncs the working tree to the server, then rebuilds/rolls out over SSH, with a
health gate before migrations run and an unconditional `pg_dump` backup before them. Full
protocol in `docs/BASE-DESIGN.md` §9.

Reverse proxy (nginx) is host-level setup this repo doesn't manage, configured once alongside
`deploy/deploy.prod.env`. Proxy to `127.0.0.1:${BACKEND_PORT}` and `127.0.0.1:${FRONTEND_PORT}`
per `docs/BASE-DESIGN.md` §9 step 8 — and never proxy `/healthz/` to the public internet (it
reports live DB/cache reachability with no auth). If [analytics](#analytics-optional) is
enabled, add a second server block for the dashboard — see `docs/UMAMI-ANALYTICS.md` for the
block and reasoning.

### Smoke-testing the prod stack locally

There's no `--dry-run` for `make deploy`, and `docker-compose.prod.yml` needs a root
`.env.prod` + `backend/.env.prod` that otherwise live only on the server (§9). To build and
boot the prod images on a dev machine before ever touching a real server:

```bash
docker compose down                              # dev and prod share container ports/names —
cp .env.prod.example .env.prod                   # stop dev first
cp backend/.env.prod.example backend/.env.prod
# fill in both — same generators as step 5, plus real DB creds and EMAIL_HOST
docker compose -f docker-compose.prod.yml --env-file .env.prod build --pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python manage.py migrate
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python manage.py collectstatic --noinput
```

**Give it a `PROJECT_NAME` in `.env.prod` different from dev's `.env`, or tear the dev stack's
volumes down first (`docker compose down -v`).** Compose scopes named volumes
(`pgdata`, `redisdata`) by `PROJECT_NAME`, and `docker-compose.yml`/`docker-compose.prod.yml`
both declare a volume literally called `pgdata` — the same `PROJECT_NAME` means the same
volume. Boot prod on top of a dev-initialized `pgdata` and Postgres reuses the dev cluster
as-is (it only runs init scripts on an empty volume), so the backend fails its healthcheck
with `password authentication failed` against credentials that look right but aren't the
ones actually baked into that volume. `docker compose -f docker-compose.prod.yml --env-file
.env.prod down -v` clears it. This is purely a same-host local-testing hazard — a real
deploy target is never also running the dev stack.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "I installed a package but it's not there" | Restarted instead of rebuilding | `docker compose up --build` — installing/upgrading changes `uv.lock`/`package-lock.json`, which changes what's baked into the image |
| Host's `.venv` shadows the container's | Bind-mounting `./backend:/app` puts the container's venv at `/app/.venv`, which the mount shadows | Already handled — `UV_PROJECT_ENVIRONMENT=/opt/venv` in `backend/Dockerfile` puts the container's venv outside the mount. Don't remove it. |
| `uv sync --locked` fails | `pyproject.toml` was hand-edited without re-locking | Never hand-edit `backend/uv.lock`. Run `uv lock` (or `uv add`, which does both) and commit the updated lockfile. |
| `flower`/`mailpit` aren't running | Dev-only tooling sits behind a compose profile | `docker compose --profile tooling up` |
| `umami`/`umami-db` aren't running | Optional analytics sits behind a compose profile | `docker compose --profile analytics up` (or `make analytics`) |
| `make build`/`npm run build` fails with `EACCES: permission denied, open '.../frontend/.next/trace'` | `docker compose up` leaves a root-owned mountpoint at `frontend/.next` on the host — a side effect of the anonymous volume declared for it in `docker-compose.yml` (the container's own writes go to that volume's real storage, not this path; this directory is an empty-but-permission-poisoned artifact of container start) | Fully remove the frontend container, not just stop it (`docker compose rm -sf frontend`), then clear the directory as root, e.g. `docker run --rm -v "$PWD/frontend:/f" alpine rm -rf /f/.next` — a plain host-user `rm -rf` fails partway through with the same permission error. Then retry the build. |
| `make test` prints "Found orphan containers" or "Network ... Resource is still in use" | The dev stack (`make up`) was running when `make test` spun up its own ephemeral Postgres/Redis on `docker-compose.test.yml` | Harmless — both stacks use different container names and ports (55432/56379 vs 5432/6379); the warnings are compose noticing the dev stack's containers/network while tearing down the test one. Tests still pass. |
| A container is up but unhealthy | Every service has a real healthcheck (§8.2) — "running" isn't "healthy" | `make ps` shows the health column; `make logs` for detail |
| Rebuild is slow every time | Stale BuildKit cache mounts or a `.dockerignore` gap shipping `.venv`/`node_modules` into the build context | Confirm `backend/.dockerignore`/`frontend/.dockerignore` still exclude them |
