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

# 4. Environment
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
python3 -c "import secrets; print(secrets.token_urlsafe(64))"                              # SECRET_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # FERNET_KEY
# stdlib only — cryptography isn't installed until step 5, and its own Fernet.generate_key()
# output is byte-for-byte the same shape as this (32 random bytes, urlsafe-base64), so either
# is a valid key; this form just works before `uv sync` has run.
# paste both into backend/.env, then fill in DB creds and PROJECT_NAME

# 5. Python + Node dependencies
cd backend && uv sync --locked && cd ..    # --locked proves pyproject.toml and uv.lock agree
cd frontend && npm ci && cd ..

# 6. Hooks
uv run --directory backend pre-commit install

# 7. Bring the stack up
docker compose up --build

# 8. First superuser
docker compose exec backend python manage.py createsuperuser

# 9. Sanity check
open http://localhost:8000/healthz/     # 200
open http://localhost:8000/api/schema/swagger-ui/
open http://localhost:3000

# 10. Commit
git add . && git commit -m "chore: initial commit from base-scaffold vX.Y.Z"
```

Steps 5–6 are `make install`; step 7 is `make up`; `make check` is the definition of done from
here on (`docs/BASE-DESIGN.md` §10.2) — the explicit steps above are what those targets
actually run, spelled out once for a first read.

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
# backend half, pinned to a release tag
cd backend
uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"

# frontend half, at the SAME tag — a mismatched pair is the #1 cause of
# "the hook returns undefined for a field the API clearly sends"
cd ../frontend
npm install "github:yourorg/notifications-app#v1.4.2:frontend"
```

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
| `backend/tools/` | Shared utilities for `config/`/`core/` — `mixins.py`, `cache.py`, `crypto.py` |
| `backend/templates/` | Override point for an installed app's templates |
| `frontend/lib/` | The shared TanStack Query client and API client every installed SDK plugs into |
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

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "I installed a package but it's not there" | Restarted instead of rebuilding | `docker compose up --build` — installing/upgrading changes `uv.lock`/`package-lock.json`, which changes what's baked into the image |
| Host's `.venv` shadows the container's | Bind-mounting `./backend:/app` puts the container's venv at `/app/.venv`, which the mount shadows | Already handled — `UV_PROJECT_ENVIRONMENT=/opt/venv` in `backend/Dockerfile` puts the container's venv outside the mount. Don't remove it. |
| `uv sync --locked` fails | `pyproject.toml` was hand-edited without re-locking | Never hand-edit `backend/uv.lock`. Run `uv lock` (or `uv add`, which does both) and commit the updated lockfile. |
| `flower`/`mailpit` aren't running | Dev-only tooling sits behind a compose profile | `docker compose --profile tooling up` |
| `umami`/`umami-db` aren't running | Optional analytics sits behind a compose profile | `docker compose --profile analytics up` (or `make analytics`) |
| A container is up but unhealthy | Every service has a real healthcheck (§8.2) — "running" isn't "healthy" | `make ps` shows the health column; `make logs` for detail |
| Rebuild is slow every time | Stale BuildKit cache mounts or a `.dockerignore` gap shipping `.venv`/`node_modules` into the build context | Confirm `backend/.dockerignore`/`frontend/.dockerignore` still exclude them |
