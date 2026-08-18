# BASE-DESIGN.md — Starter Scaffold Architecture

> **Companion documents:** `APP-DESIGN.md` (the installable app packages), `INTEGRATION-GUIDE.md` (how a host wires them in), `CLAUDE-CODE-GUIDE-BASE.md` (how to actually build this scaffold with an AI agent).

## Table of contents

1. [Purpose & Ownership Model](#1-purpose--ownership-model)
2. [Monorepo Directory Structure](#2-monorepo-directory-structure)
3. [Pre-Configured Base Stack](#3-pre-configured-base-stack)
4. [Toolchain, Dependencies & Environment Strategy](#4-toolchain-dependencies--environment-strategy)
5. [Code Quality & Testing Setup](#5-code-quality--testing-setup)
6. [Inter-App Integration Layer (`core/`)](#6-inter-app-integration-layer-core)
7. [Continuous Integration](#7-continuous-integration)
8. [Docker & Compose (dev / prod)](#8-docker--compose-dev--prod)
9. [Deployment](#9-deployment)
10. [Bootstrapping & Setup Walkthrough](#10-bootstrapping--setup-walkthrough)
11. [Ecosystem Tooling](#11-ecosystem-tooling)

---

## 1. Purpose & Ownership Model

The base repository is a **one-time starter kit**, not a living upstream dependency. It bundles a Django 6 (ASGI) backend, a Next.js App Router frontend, and Docker Compose orchestration into a single monorepo template. A new project clones it, deletes its `.git` history, and starts its own — there is no ongoing `git pull` from this template into existing projects.

That one decision simplifies ownership considerably. There are only two categories of code in a running project, not three:

| Category | What it is | Editable? |
|---|---|---|
| **Project code** (`backend/`, `frontend/`, everything cloned from this scaffold plus everything written afterward) | Yours from the moment `.git` is deleted — there's no distinction between "scaffold-origin" and "written later" | Freely editable, always |
| **Installed backend app packages** (`.venv/…/site-packages`, via `uv`) | Versioned, third-party, read-only reusable apps — see `APP-DESIGN.md` | Never edited directly — see `INTEGRATION-GUIDE.md` §1 |
| **Installed frontend app packages** (`frontend/node_modules`, via `npm`) | The same reusable apps' TypeScript/React half — typed hooks, fetchers — see `APP-DESIGN.md` | Never edited directly — same rule, same reasoning |

If the scaffold itself improves later (a better `Dockerfile`, a new `tools/` helper), that's backported by hand into existing projects if wanted — never pulled automatically. This trades "automatic updates" for "no merge-conflict risk, ever," which is the right trade once the base stops being a dependency and becomes a starting point.

**One consequence worth stating outright:** because there's no upstream pull, the scaffold's own quality bar has to be high on day one — a mistake baked in here propagates into every project cloned from it and then has to be fixed N times. That's the reasoning behind §5 and §7 existing at all: the scaffold ships with its own linting, typing, tests, and CI configured, so a new project inherits the guardrails rather than being asked to add them later.

## 2. Monorepo Directory Structure

```
my-client-project/
├── .git/                            # single top-level git repository for the whole project
├── .gitignore                       # .env*, node_modules, .venv, __pycache__, .next, media/
├── .dockerignore                    # see §8.1 — must exist, or builds ship .venv/node_modules
├── .env                             # [project-owned, gitignored] compose-level vars
├── .env.example                     # [tracked] template for the above
├── .pre-commit-config.yaml          # ruff, mypy, prettier, eslint — see §5.1
├── .python-version                  # e.g. "3.14" — matches the Docker base image
├── CLAUDE.md                        # agent instructions — generated at clone time, see §10
├── docs/
│   ├── APP-DESIGN.md                # copied in at clone time so agents can read them locally
│   ├── BASE-DESIGN.md
│   └── INTEGRATION-GUIDE.md
├── .github/
│   └── workflows/
│       └── ci.yml                   # host-project CI, see §7
├── docker-compose.yml               # local dev orchestration
├── docker-compose.prod.yml          # production orchestration — see §8.2
├── docker-compose.test.yml          # ephemeral Postgres/Redis for the test suite, §5.3
├── Makefile                         # one memorable entrypoint per common task, see §10.2
├── deploy/                          # [project-owned] deployment tooling, see §9
│   ├── deploy-prod.sh
│   └── deploy.prod.env.example      # template — real deploy.prod.env is gitignored
├── frontend/                        # Next.js App Router (TypeScript), pre-wired to backend
│   ├── Dockerfile                   # dev image
│   ├── Dockerfile.prod              # production image, see §8.1
│   ├── .dockerignore
│   ├── package.json
│   ├── package-lock.json            # committed; `npm ci` everywhere, never `npm install` in CI
│   ├── tsconfig.json                # "strict": true
│   ├── next.config.ts               # output: "standalone" — see §8.1
│   ├── eslint.config.mjs
│   ├── vitest.config.ts
│   ├── app/
│   │   ├── layout.tsx               # mounts QueryClientProvider
│   │   └── api/health/route.ts      # frontend healthcheck target, see §8.2
│   └── lib/
│       ├── query-client.ts          # shared TanStack Query client — every installed
│       │                              frontend app-package SDK plugs into this
│       └── api-client.ts            # shared fetcher: base URL, credentials, error shape
└── backend/
    ├── pyproject.toml               # deps, dependency-groups, ruff/mypy/pytest config — §4
    ├── uv.lock                      # COMMITTED — the reproducibility guarantee
    ├── .env.example
    ├── .env.prod.example
    ├── Dockerfile                   # dev image
    ├── Dockerfile.prod              # production image, see §8.1
    ├── .dockerignore
    ├── manage.py
    ├── conftest.py                  # project-wide pytest fixtures, see §5.2
    ├── config/                      # settings.py, urls.py, asgi.py, wsgi.py, celery.py
    │   ├── settings.py
    │   ├── logging.py               # dev=colored console, prod=JSON — see §3
    │   └── views.py                 # cross-cutting views — the /healthz/ endpoint §8.2 uses
    ├── core/                        # project-owned integration & glue layer
    │   ├── apps.py                  # AppConfig; ready() imports core/signals.py
    │   ├── signals.py               # inter-app signal listeners
    │   ├── services/                # cross-app business logic orchestrators
    │   ├── views/                   # subclasses/overrides of an installed app's views
    │   └── tests/                   # tests for signals, services, view overrides
    ├── tools/                       # shared utilities — mixins.py, cache.py, crypto.py
    ├── templates/                   # override point for an installed app's templates
    └── locale/
```

No `.gitmodules`, no `apps/` folder, no dynamic settings-composition machinery, and **no `requirements.txt`**. Everything a previous iteration of this design solved with auto-discovery is now solved simply by this being a normal, explicit Django project — because nothing here needs to survive being merged with an upstream update anymore.

Two additions to the tree worth explaining:

- **`docs/`** — the three design documents are copied into every project at clone time. Not for humans (who can read them in the template repo) but for agents: Claude Code can read a local file cheaply and reliably, and `CLAUDE.md` pointing at `docs/INTEGRATION-GUIDE.md` is far more likely to actually be followed than a URL.
- **`Makefile`** — a thin, memorable interface over the real commands. Its real value is that `CLAUDE.md` can say "run `make test`" once instead of restating a six-flag `uv run pytest` invocation everywhere, and the invocation can then change in one place.

## 3. Pre-Configured Base Stack

- **Django 6 on ASGI**, served by Uvicorn (not Gunicorn/WSGI). `uvicorn[standard]` already speaks WebSocket and works fine with Channels if a project needs one later — see "WebSockets" below. `daphne` is the reference ASGI server in Channels' own docs, not a requirement.
- **Django REST Framework + `drf-spectacular`** for the API and its OpenAPI/Swagger schema.
- **Postgres 17** as the only supported database, in dev, test, and prod. No SQLite anywhere, including tests — see §5.3.
- **Celery + Redis** for background jobs needing chaining, retries, or scheduling, with `django-celery-beat`'s `DatabaseScheduler` for periodic tasks (see §6); Django's native `django.tasks` framework for simple one-off jobs (single email, single notification) that don't need Celery's overhead.
- **`django-jazzmin`** for the admin theme, configured via `JAZZMIN_SETTINGS` in `config/settings.py`.
- **`django-cors-headers`, `whitenoise`**, preconfigured.
- **Logging split by environment** — `config/logging.py` returns a colored, human-readable console config when `DEBUG` is on and a `structlog`-based JSON config when it isn't. This is deliberate: JSON in dev is unreadable to a person, and colored text in prod is unparseable by any log aggregator, so a single config is wrong in one environment no matter which you pick. Both configs include a request ID so a single request's log lines can be correlated — the `ContextVar`, the request-ID middleware, and the `logging.Filter` that reads it all live in `config/logging.py` alongside `build_logging_config()`, since all three exist only to serve it. This needs no new dependency: `contextvars` and `logging.Filter` are both stdlib.

  The request-ID middleware is a raw, non-`MiddlewareMixin` async-only class (`async_capable = True`, `sync_capable = False`, `async def __call__`). Those two class attributes only tell Django's `load_middleware` how to build *that* middleware's own wrapper — they say nothing to `inspect.iscoroutinefunction(instance)`, the separate check any *other* middleware wrapping it (e.g. `SecurityMiddleware`) uses to decide whether to `await` it. `MiddlewareMixin`-based middleware calls `inspect.markcoroutinefunction(self)` internally to make itself visible to that check; a raw async-only middleware class has to do the same in its own `__init__`, or every outer middleware calls it without awaiting and crashes on the returned coroutine — see `docs/CORRECTIONS.md` #12, where this broke every real request (ASGI and WSGI both) until fixed. Any future raw async middleware added to `core/` or `config/` needs this same `markcoroutinefunction(self)` call.
- **Sentry**, initialized in `config/settings.py` behind a `SENTRY_DSN` env var that's empty by default (so it's inert locally and in CI, active the moment a DSN is set). This is included rather than left out because the combination of Celery workers, ASGI concurrency, and N installed third-party app packages makes "an exception happened somewhere and nobody knew" the default failure mode otherwise. Wire the Django, Celery, and Redis integrations, and set `traces_sample_rate` low (0.1) rather than off, so slow-endpoint data exists when someone asks.
- **`tools/`** — `mixins.py` (shared DRF mixins/error formats), `cache.py` (caching helpers), `crypto.py` (wraps a `Fernet` cipher built from `FERNET_KEY` in `.env`). These exist for `config/` and `core/` to use — see `INTEGRATION-GUIDE.md` §6 for why installed app packages don't reach into this folder.

  `tools/mixins.py`'s `standard_exception_handler` is wired as `REST_FRAMEWORK["EXCEPTION_HANDLER"]`, so every DRF-raised error — not only views that opt into a mixin — renders in one envelope:

  ```json
  {"error": {"code": "validation_error", "message": "...", "details": {}, "request_id": "..."}}
  ```

  `details` is always present (`{}` when nothing is field-level, so a client never has to branch on whether the key exists). `request_id` is the same correlation ID `config/logging.py` stamps on every log line. `code` is a stable, machine-readable string clients branch on — adding one is a minor change, renaming one is breaking. The full set: `validation_error`, `parse_error`, `not_authenticated`, `authentication_failed`, `permission_denied`, `not_found`, `method_not_allowed`, `throttled`, `server_error`. An unhandled exception is logged (`logger.exception`) before being turned into a `server_error` envelope, so it still reaches Sentry; `message` on a `server_error` is generic with `DEBUG` off and carries the real exception text with it on. Headers DRF already sets — `Retry-After` on `throttled`, `WWW-Authenticate` on `not_authenticated` — are untouched, since the handler rewrites only `response.data`. This is the shape `APP-DESIGN.md` §4 asks every installed app package to bundle an internal equivalent of.
- **Frontend baseline** — Next.js App Router (TypeScript, `strict`) with `@tanstack/react-query` and a shared API client already set up in `frontend/lib/`, so an installed frontend app-package's hooks have a consistent client to plug into out of the box instead of every app package bootstrapping its own.

**Deliberately not included: authentication.** `SIMPLE_JWT` or any other auth configuration does not belong in the base scaffold — auth is its own standalone, versioned app package (per `APP-DESIGN.md`), installed into a project the same way payments or notifications would be. This keeps the scaffold auth-agnostic and keeps a project free to swap auth strategies without touching the base at all.

### WebSockets

**Deliberately excluded, for the same reason as auth.** Django has no WebSocket handling of
its own — adding it means `django-channels` plus a channel layer (Redis-backed, same as
everything else here), and most projects never open a socket. `config/asgi.py` as shipped by
this scaffold only calls `get_asgi_application()`, which handles the `http` scope and nothing
else. That's the full ASGI foundation a project gets by default: real WebSocket support is an
opt-in a project adds when it actually needs one, not baked in speculatively.

`uvicorn[standard]` — already the pinned ASGI server, see above — speaks WebSocket out of the
box and works with Channels; nothing about the server needs to change to add it.

**When a project does need it**, the protocol is the same shape as everything else in this
scaffold: add the dependency, then wire it explicitly in `config/`, never by auto-discovery.

1. `uv add channels channels-redis` to `backend/pyproject.toml`.
2. Compose `http` and `websocket` scopes in `config/asgi.py` with `ProtocolTypeRouter` — the
   host is the mediator for the `websocket` scope in exactly the same sense `config/urls.py`
   is the mediator for `http`:

   ```python
   # config/asgi.py
   import os

   from django.core.asgi import get_asgi_application

   os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

   # get_asgi_application() MUST run before any consumer is imported — consumers pull in
   # models, and importing a model before Django's app registry is populated raises
   # AppRegistryNotReady. This ordering is the one part of this file that isn't optional.
   django_asgi_app = get_asgi_application()

   from channels.auth import AuthMiddlewareStack
   from channels.routing import ProtocolTypeRouter, URLRouter

   # from notifications_app.routing import websocket_urlpatterns as notifications_ws

   application = ProtocolTypeRouter(
       {
           "http": django_asgi_app,
           "websocket": AuthMiddlewareStack(
               URLRouter(
                   [
                       # *notifications_ws,
                   ]
               )
           ),
       }
   )
   ```

3. Update `docker-compose*.yml`'s `backend` service — no change needed to the run command
   itself (`uvicorn config.asgi:application` already serves both scopes once `channels` is
   installed), but production nginx needs an explicit block for the WebSocket path that
   forwards the `Upgrade`/`Connection` headers nginx doesn't pass through by default. This is
   a deploy-side change, not only an application-code one, and easy to forget because
   everything works locally without it (`runserver`/Uvicorn don't need it).

See `APP-DESIGN.md` §6 ("Realtime") for how an installed app package contributes routes and
consumers into this composition.

### Auth integration

**Deliberately excluded, same reasoning as above** — see "Deliberately not included:
authentication" above. This subsection exists because the base stack, as shipped, is
*not* configured for it: `CORS_ALLOW_CREDENTIALS` defaults to `False`,
`CSRF_TRUSTED_ORIGINS` is empty, and `frontend/lib/api-client.ts`'s default
`ApiClient` instance sends `credentials: "same-origin"`. Cross-origin cookie auth
silently does nothing until all of the following change together — an installed
cookie-session auth app's setup instructions (its own `README.md`, per
`INTEGRATION-GUIDE.md` §2) must say to:

1. Set `CORS_ALLOW_CREDENTIALS=True` in `.env`/`.env.prod`
   (`backend/config/settings.py`). This is incompatible with a wildcard origin — the
   browser rejects a wildcard `Access-Control-Allow-Origin` on a credentialed request —
   so `CORS_ALLOWED_ORIGINS` must stay an explicit list, never `CORS_ALLOW_ALL_ORIGINS`,
   in every environment where this is on.
2. Set `CSRF_TRUSTED_ORIGINS` to the frontend's origin(s).
3. Construct the frontend's `ApiClient` with `credentials: "include"`
   (`new ApiClient({ credentials: "include" })` in `frontend/lib/api-client.ts`) instead
   of relying on the `"same-origin"` default — once, at construction, not per call site.
4. Nothing else to add for CSRF itself: `frontend/lib/api-client.ts` already reads the
   `csrftoken` cookie and sends it as `X-CSRFToken` on unsafe methods whenever
   `credentials !== "omit"`. This works specifically because `CSRF_COOKIE_HTTPONLY = False`
   in `backend/config/settings.py` keeps that cookie JS-readable — don't flip that back to
   `True`, it would silently break every write request.

See `APP-DESIGN.md` §12's frontend security checklist for the cross-reference: an app's
own frontend package must rely on this host-level handling rather than inventing its own
token storage.

## 4. Toolchain, Dependencies & Environment Strategy

### 4.1 `uv` is the only Python package manager

One tool, one lockfile, one install command — in local dev, in Docker, in CI, and on the production server. `requirements.txt` does not exist in this scaffold. The reasons this matters more here than in a typical project:

- Installed app packages come from `git+https://…@vX.Y.Z#subdirectory=backend` refs. `uv.lock` resolves those to exact commit hashes, so "we're on v1.4.2" means the same bytes everywhere. A `requirements.txt` line pointing at a tag does not guarantee that — a tag can be moved.
- All apps resolve into **one shared environment** (see `APP-DESIGN.md` §1.1). A real resolver that fails loudly on a conflict is worth a great deal compared to `pip`'s first-wins-then-breaks-at-runtime behavior.
- Dependency groups (PEP 735) keep test/lint tooling out of production images with a single `--no-dev` flag, instead of a second requirements file that drifts.

### 4.2 `backend/pyproject.toml`

```toml
[project]
name = "my-client-project"
version = "0.1.0"
requires-python = ">=3.14"           # a HOST may pin tightly; app packages must not (§APP 1.1)

dependencies = [
    # ---- platform: the host decides the exact versions everyone runs against
    "django>=6.0,<6.1",
    "djangorestframework>=3.15,<4.0",
    "drf-spectacular>=0.27,<1.0",
    "django-cors-headers>=4.6,<5.0",
    "django-jazzmin>=3.0,<4.0",
    "django-celery-beat>=2.7,<3.0",
    "celery[redis]>=5.4,<6.0",
    "psycopg[binary]>=3.2,<4.0",
    "python-decouple>=3.8,<4.0",
    "whitenoise>=6.8,<7.0",
    "uvicorn[standard]>=0.34,<1.0",
    "cryptography>=44,<46",
    "structlog>=25,<26",
    "sentry-sdk[django,celery]>=2.20,<3.0",
    # ---- installed app packages get appended here by `uv add`, one line each
]

[dependency-groups]
dev = [
    "ruff>=0.12",
    "mypy>=1.14",
    "django-stubs[compatible-mypy]>=5.1",
    "djangorestframework-stubs>=3.15",
    "pre-commit>=4.0",
    "django-debug-toolbar>=5.0",
    "django-extensions>=3.2",        # shell_plus, show_urls
]
test = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "pytest-cov>=6.0",
    "pytest-xdist>=3.6",
    "factory-boy>=3.3",              # needed to use installed apps' factories, APP-DESIGN §7.3
    "freezegun>=1.5",
]

[tool.uv]
default-groups = ["dev", "test"]

# Uncomment ONE of these blocks while developing an app package against this project.
# Swap it back to the pinned git ref before committing — see INTEGRATION-GUIDE.md §7.
# [tool.uv.sources]
# notifications-app = { path = "../notifications-app/backend", editable = true }
```

Ruff, mypy, pytest and coverage config live in this same file — see §5. The `[tool.uv.sources]` comment block is load-bearing documentation: it's the sanctioned way to point a host at a local app checkout, and having it present-but-commented is what stops someone inventing a worse method.

### 4.3 Settings & environment

`config/settings.py` is a single, standard Django settings file — no settings package, no composer, no filesystem scanning. Values come from `.env` via `python-decouple`:

```python
from decouple import Csv, config

DEBUG = config("DEBUG", default=False, cast=bool)
SECRET_KEY = config("SECRET_KEY")                       # no default — fail loudly
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())
FERNET_KEY = config("FERNET_KEY")
SENTRY_DSN = config("SENTRY_DSN", default="")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("CONN_MAX_AGE", default=60, cast=int),
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                      "LOCATION": config("REDIS_URL")}}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {},     # app installs add their own scopes here
}

INSTALLED_APPS = [
    # jazzmin MUST precede django.contrib.admin — it overrides the admin templates via
    # Django's app-directories loader, which resolves to the first match in this list.
    # Reversed, the admin still renders, just silently unthemed — see CORRECTIONS.md #4.
    "jazzmin",
    "django.contrib.admin",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
    "core",
    # ---- installed app packages get added here, one line each, per their own README
]

# Env-driven, defaulting to "secure unless DEBUG says otherwise" — see CORRECTIONS.md #3
# for why SECURE_HSTS_SECONDS is the one exception that does NOT inherit that default.
_SECURE_DEFAULT = not DEBUG
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=_SECURE_DEFAULT, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
# Defaults to 0 in every environment, including prod: a year of HSTS is effectively
# irreversible for the domain and every subdomain, so turning it on is a deliberate,
# explicit act (backend/.env.prod.example sets 31536000), never an inherited default.
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
# Only trust X-Forwarded-Proto when we know a proxy sits in front — trusting it
# unconditionally is a spoofing vector the moment the container is reachable directly.
TRUST_PROXY_SSL_HEADER = config("TRUST_PROXY_SSL_HEADER", default=_SECURE_DEFAULT, cast=bool)
if TRUST_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must stay JS-readable — the Next.js frontend sends it as a header
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = build_logging_config(debug=DEBUG)   # from config/logging.py, see §3
```

**Startup validation is worth the twenty lines it costs.** Add a Django system check (or a short block at the end of `settings.py`) asserting that, when `DEBUG` is off: `SECRET_KEY` isn't the example value, `ALLOWED_HOSTS` isn't empty or `["*"]`, and every `.env` key the installed apps declared as required is actually set. A misconfigured production deploy that boots and *then* misbehaves costs far more than one that refuses to boot.

**Installed app packages are configured by copy-pasting the block from that app's own `README.md`** into this file — `INSTALLED_APPS`, `MIDDLEWARE`, and `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` entries, plus adding any required keys to `.env`/`.env.example`. There's no dynamic merge step; the full protocol is in `INTEGRATION-GUIDE.md` §2, and it's the same protocol whether a human or an AI agent is doing the wiring.

### 4.4 Env file inventory

Four `.env` files, each with a tracked `.example`, and a clear rule about which is which:

| File | Scope | Committed? |
|---|---|---|
| `.env` | Compose-level interpolation only — `PROJECT_NAME`, host ports | No (`.env.example` is) |
| `backend/.env` | Django dev settings, DB creds, Redis URL, app package keys | No (`.env.example` is) |
| `backend/.env.prod` | Same keys, production values | No — **lives only on the server**, never synced |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` and friends | No |

The "lives only on the server" rule for `.env.prod` is enforced by `deploy-prod.sh`'s rsync excludes (§9) and is worth keeping strict: the moment production secrets exist on a developer laptop, they exist in that laptop's backups.

## 5. Code Quality & Testing Setup

The scaffold ships with all of this configured, so a new project starts with the guardrails rather than acquiring them later.

### 5.1 Lint, format, type-check

Same toolchain as the app packages (`APP-DESIGN.md` §3), configured in `backend/pyproject.toml`, plus one host-specific addition worth calling out:

**This table ships commented out.** The scaffold contains no project-specific content, so it can't name apps a project may never install — and a partially-populated list reads as authoritative when it isn't. Ship the `per-file-ignores` block live (it's app-agnostic and needed from day one) and the `banned-api` entries as commented examples; `INTEGRATION-GUIDE.md` §2 step 9 is what adds a real line per installed app.

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
# Machine-enforces the mediator rule: only core/ and config/ may import app packages.
# Add one line per installed app — INTEGRATION-GUIDE.md §2 step 9 makes this a wiring step.
"notifications_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"
"payments_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"

[tool.ruff.lint.per-file-ignores]
"core/**" = ["TID251"]       # core/ is the mediator — it's ALLOWED to know two apps exist
"config/**" = ["TID251"]     # settings.py/urls.py reference app modules by design
"*/migrations/*" = ["E501", "RUF012"]
```

This turns the "zero direct imports between two app packages" checklist item in `INTEGRATION-GUIDE.md` §9 from a grep somebody has to remember into a lint error somebody cannot merge past. It's the single highest-leverage config line in this scaffold.

Frontend: ESLint (`next/core-web-vitals` + `@typescript-eslint`), Prettier, and `tsc --noEmit` in CI. `tsconfig.json` sets `"strict": true` and, ideally, `"noUncheckedIndexedAccess": true`.

`.pre-commit-config.yaml` uses **`repo: local` hooks with `language: system`** for ruff, ruff-format, mypy, eslint and prettier, invoked through `uv run` / `npx` so they resolve from `uv.lock` and `package-lock.json`. Mirror-based hooks with a pinned `rev` are wrong for these: mypy here is `strict` with `mypy_django_plugin` and a `django_settings_module`, so it needs Django and the whole backend importable, which pre-commit's isolated venv doesn't provide — and a pinned `rev` means pre-commit and CI can run two different formatter versions. Only genuinely environment-independent hooks stay as pinned mirrors: `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files`, `detect-private-key`, `check-yaml`, `check-toml`. Add the factories grep from §5.2 as a local hook too. `uv run --directory backend pre-commit install` is step 6 of the bootstrap in §10.

### 5.2 pytest configuration & conftest hierarchy

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
pythonpath = ["."]
testpaths = ["core/tests", "config/tests", "tools/tests"]
python_files = ["test_*.py"]
addopts = """
  -ra --strict-markers --strict-config
  --cov=core --cov=tools --cov=config
  --cov-report=term-missing --cov-fail-under=80
"""
markers = [
    "slow: excluded from the default run, opt in with -m slow",
    "integration: crosses a real DB/broker boundary rather than mocking it",
]
filterwarnings = ["error::DeprecationWarning"]
```

**`testpaths` deliberately excludes installed app packages.** An app's own suite is its own repo's CI gate (`APP-DESIGN.md` §10); re-running it here would test third-party code you can't fix from this repo and would slow every local run. What this project tests is *its own* code — `core/`, `tools/`, `config/` — which is exactly the code no app's test suite covers.

Fixture hierarchy:

```
backend/conftest.py                # project-wide: api_client, user, admin_user, auth_client
backend/core/tests/conftest.py     # cross-app fixtures — a seeded cart + payment, etc.
```

Cross-app fixtures are where installed apps' `factories.py` (`APP-DESIGN.md` §7.3) earns its place:

```python
# backend/core/tests/conftest.py
import pytest
from cart_app.factories import CartFactory, CartItemFactory
from payments_app.factories import PaymentMethodFactory


@pytest.fixture
def checkout_ready_user(user):
    cart = CartFactory(user=user)
    CartItemFactory.create_batch(3, cart=cart)
    PaymentMethodFactory(user=user, is_default=True)
    return user
```

Importing another app's factories from `core/tests/` is sanctioned and expected; importing them from `core/services/` or any other production code is a bug.

**This rule can't be enforced with ruff in a host project**, and it's worth understanding why, because the reasoning applies to any future rule of this shape. `banned-api` violations all report as `TID251`, and `per-file-ignores` disables a rule *code* for a path. Since `core/**` must already ignore `TID251` (production `core/` legitimately imports app packages — that's its purpose), any factories entry in `banned-api` is silently disabled throughout `core/`, including the production code you wanted to catch. There's no way to re-enable a rule for a subpath. So enforce it with grep instead, in pre-commit and in CI:

```bash
# fails if production core/ imports factories; core/tests/ is fine
! grep -rn '\.factories' backend/core --include='*.py' | grep -v '/tests/'
```

Note this asymmetry with app packages: in an app repo the same rule *does* work via ruff, because its test tree lives outside `src/` and can be cleanly exempted (`APP-DESIGN.md` §3.1). The host's problem is that `core/` and `core/tests/` share one subtree.

### 5.3 Tests run on Postgres

`docker-compose.test.yml` provides an ephemeral Postgres + Redis on non-default ports, so a test run never collides with the dev stack:

```yaml
services:
  test-db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: test_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports: ["55432:5432"]
    tmpfs: /var/lib/postgresql/data     # RAM-backed: meaningfully faster, nothing to clean up
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
  test-redis:
    image: redis:7-alpine
    ports: ["56379:6379"]
    # `up -d --wait` only blocks on services that declare a healthcheck — without one,
    # test-redis could still be starting when pytest connects.
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
```

```make
test:
	docker compose -f docker-compose.test.yml up -d --wait
	cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow"
	docker compose -f docker-compose.test.yml down
```

The extra `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`/`REDIS_URL` exports above are
required, not optional: without them the suite falls back to `backend/.env`'s dev credentials
and `redis://redis:6379/0`, neither of which exists against the `test-db`/`test-redis`
containers this target just started.

`--reuse-db` (pytest-django) is worth adding to the local loop once migrations stabilize; CI always builds fresh.

### 5.4 What the host project's tests must cover

Everything in `core/` is custom, project-owned code that no app's test suite covers — because no app knows `core/` exists. Concretely:

- **Signal receivers** — fire the signal directly and assert the receiver's effect, rather than driving a full request cycle. See `INTEGRATION-GUIDE.md` §4 for the worked example.
- **`core/services/` orchestrators** — call them as plain functions against a test DB; assert both the return value and the side effects.
- **`core/views/` overrides** — `APIClient`, status codes, response shape.
- **`config/` wiring smoke tests** — one test asserting `/api/schema/` returns 200 and contains every mounted app's tag, and one asserting every scope referenced by a `throttle_scope` in the codebase exists in `DEFAULT_THROTTLE_RATES`. These two catch the most common integration mistakes in this whole architecture, and they cost about fifteen lines.

## 6. Inter-App Integration Layer (`core/`)

Installed app packages must stay 100% decoupled from one another — no app ever imports another app. Anything that connects two apps (payments completing and triggering a notification, checkout reading the cart) is wired in `backend/core/`:

- **`core/signals.py`** — receivers that listen for one app's Django signal and call another app's service method in response. Fire-and-forget, event-driven.
- **`core/services/`** — orchestration functions for workflows that need a direct, synchronous composition of multiple apps' own `services.py` interfaces (e.g. a checkout flow).

`core` is registered in `INSTALLED_APPS` with its own `AppConfig`, whose `ready()` imports `core/signals.py` so every receiver connects at startup. Full worked examples of both patterns live in `INTEGRATION-GUIDE.md` §4 — the short version is: apps expose events and callables, `core/` is the only code allowed to know two apps exist at once.

**A receiver that does real work belongs in a task, not in the receiver.** A signal receiver runs synchronously inside the sender's transaction. If the work is slow or can fail independently (sending an email, calling a payment provider), the receiver should enqueue a Celery task and return — and it should enqueue with `transaction.on_commit(...)` so the task never runs against a transaction that later rolls back. This is the most common source of "the notification fired for a payment that didn't actually complete."

Periodic tasks follow the same "app recommends, host wires in" pattern rather than auto-registering: an app's `README.md` documents any schedule it needs (`APP-DESIGN.md` §8), but nothing about installing the app creates the schedule automatically. The host explicitly creates the corresponding `django_celery_beat.models.PeriodicTask` entry — via Django admin, or better, a data migration in `core/` so it's reproducible and code-reviewed rather than clicked into a production admin panel once and forgotten. That keeps the actual beat schedule project-owned and inspectable in one place.

## 7. Continuous Integration

The host project's CI is smaller than an app package's — it doesn't build wheels or check version lockstep — but it exists for the same reason: the checklists in `INTEGRATION-GUIDE.md` §9 shouldn't depend on a human remembering them.

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push: { branches: [main] }
  pull_request:

env:
  PYTHON_VERSION: "3.14"
  NODE_VERSION: "22"

jobs:
  backend-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true, cache-dependency-glob: backend/uv.lock }
      - run: uv sync --locked
        working-directory: backend
      # --locked is the point: it FAILS if pyproject.toml and uv.lock disagree, which is
      # how a hand-edited dependency line without a re-lock gets caught.
      - run: uv run ruff check --output-format=github .
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run mypy .
        working-directory: backend

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env: { POSTGRES_DB: test_db, POSTGRES_USER: postgres, POSTGRES_PASSWORD: postgres }
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping" --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["6379:6379"]
    env:
      POSTGRES_HOST: localhost
      POSTGRES_DB: test_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      REDIS_URL: redis://localhost:6379/0
      SECRET_KEY: ci-only-not-a-secret
      FERNET_KEY: ${{ secrets.CI_FERNET_KEY }}
      ALLOWED_HOSTS: localhost
      DEBUG: "False"
      # Without this, `check --deploy --fail-level WARNING` fails on security.W004 — see
      # CORRECTIONS.md #3 for why the app itself never defaults this value to non-zero.
      SECURE_HSTS_SECONDS: "31536000"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true, cache-dependency-glob: backend/uv.lock }
      - run: uv sync --locked
        working-directory: backend
      - name: Missing migrations check
        run: uv run python manage.py makemigrations --check --dry-run
        working-directory: backend
      - name: Django deployment checks
        run: uv run python manage.py check --deploy --fail-level WARNING
        working-directory: backend
      - run: uv run pytest -n auto
        working-directory: backend

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run test -- --run
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
        env: { NEXT_PUBLIC_API_URL: http://localhost:8000 }

  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build production images (proves the prod path still builds)
        run: |
          docker buildx build -f backend/Dockerfile.prod backend --load -t app-backend:ci
          docker buildx build -f frontend/Dockerfile.prod frontend --load -t app-frontend:ci \
            --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000
      - name: Smoke-test the backend image boots
        run: |
          docker run --rm app-backend:ci python -c "import django; print(django.get_version())"

  security-audit:
    runs-on: ubuntu-latest
    continue-on-error: true       # advisory until the noise level is known; then promote
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uvx pip-audit --strict -r <(uv export --no-dev --format requirements-txt)
        shell: bash
        working-directory: backend
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm audit --audit-level=high
        working-directory: frontend
```

**Why `docker-build` is a job and not an afterthought:** in this architecture, installing an app package changes `uv.lock`, which changes what gets baked into the image. A PR that adds an app can pass every test and still produce an image that fails to build (a native dependency needing a system library, a private git ref CI can't reach). Catching that in CI rather than in `deploy-prod.sh` is worth the two minutes.

**Renovate** (`renovate.json`) keeps the pins fresh: `uv.lock`, `package-lock.json`, the Docker base image digests, GitHub Action versions, pre-commit `rev`s, and — most importantly for this architecture — the `git+…@vX.Y.Z` app package refs. Group patch/minor into a weekly PR; keep majors separate. A pinned-everything architecture without an update bot doesn't stay pinned, it stays *stale*, which is worse.

## 8. Docker & Compose (dev / prod)

Dev and production run from different Dockerfiles and different compose files — dev optimizes for fast iteration (bind-mounted source, migrate-on-boot, hot reload), prod optimizes for reproducibility and security (baked image, non-root, no migrate-on-boot, explicit health-gated rollout). Sharing one Dockerfile between them tends to compromise both.

### 8.1 Dockerfiles

**`.dockerignore` first**, because without it every build ships a stale `.venv` and a 400MB `node_modules` into the context, which is both slow and a real source of "it works in the container because an old artifact is in there":

```gitignore
# backend/.dockerignore
.venv
__pycache__/
*.py[cod]
.pytest_cache
.ruff_cache
.mypy_cache
.env
.env.*
!.env.example
logs/
media/
staticfiles/
.git
```

```gitignore
# frontend/.dockerignore
node_modules
.next
.env.local
.git
coverage
```

**`backend/Dockerfile.prod`** — `uv`-based, multi-stage, non-root, with BuildKit cache mounts so a one-dependency change doesn't re-download the tree:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
# UV_COMPILE_BYTECODE moves .pyc generation to build time — pure win for container cold starts.
# UV_LINK_MODE=copy is required with cache mounts: uv's default hardlinks point into the
# cache mount, which doesn't exist in the final stage, producing runtime ImportErrors.

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev pkg-config git \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: dependencies only. Cached until pyproject.toml/uv.lock actually change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=ssh \
    uv sync --locked --no-install-project --no-dev --no-editable

# Layer 2: the project itself. Invalidated by any code change, which is fine — it's fast.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ------------------------------------------------------------------ runtime
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 postgresql-client curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
RUN mkdir -p /app/logs /app/static /app/staticfiles /app/media \
    && chown -R appuser:appuser /app/logs /app/staticfiles /app/media

USER appuser
EXPOSE 8000
CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "3", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

Notes on the deliberate choices:
- **`git` is installed in the builder only** — it's needed to resolve the `git+https://…` app package refs, and it has no business being in the runtime image.
- **`--mount=type=ssh`** supports private app package repos without ever putting a credential in a layer (see `APP-DESIGN.md` §1.2). Build with `docker buildx build --ssh default`, or swap to `--mount=type=secret,id=gh_token` for the token flow.
- **No migrate on boot.** See §9 for why that's a deploy-script step.
- **`--proxy-headers`** matters because prod binds to `127.0.0.1` behind nginx; without it every client IP in your logs is the proxy's.
- **Pin the base image by digest** (`python:3.14-slim@sha256:…`) in a real project and let Renovate bump it. Reproducibility is the whole point of the prod image; a floating tag quietly undermines it.
- **Worker count** should be derived from the host's CPU count rather than hardcoded to 3 — pass it in as an env var (`UVICORN_WORKERS`) so the same image runs correctly on a 2-core VPS and a 16-core box.

**`backend/Dockerfile`** (dev) — same builder, but keeps dev/test groups and runs the autoreloading server:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=0 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev pkg-config git postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=ssh \
    uv sync --locked --no-install-project
COPY . /app
RUN mkdir -p /app/logs /app/static /app/staticfiles /app/media
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
```

Dev stays single-stage on purpose: with the source bind-mounted, a builder stage buys nothing and costs rebuild time. Dev runs as root deliberately too — bind-mounted files owned by your host user are otherwise unwritable by a container user, which breaks `makemigrations` in the most annoying possible way. That trade is acceptable in dev and unacceptable in prod, which is precisely why they're separate files.

**One `.venv` gotcha with bind mounts:** if you bind-mount `./backend:/app` and the container's venv is at `/app/.venv`, your host's `.venv` shadows the container's. Either put the container venv outside the mount (`UV_PROJECT_ENVIRONMENT=/opt/venv`) or add an anonymous volume for `/app/.venv` in compose. The scaffold uses the first option — it's less surprising.

**`frontend/Dockerfile.prod`** — standard Next.js multi-stage, but using `output: "standalone"`:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# NEXT_PUBLIC_* is inlined into the client bundle at BUILD time — it must be a build ARG,
# not a runtime env var. Changing it means rebuilding the image, not restarting it.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 nodejs && adduser -S -u 10001 -G nodejs nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
```

`output: "standalone"` in `next.config.ts` makes Next trace exactly which `node_modules` files the server actually needs and emit them into `.next/standalone`. Copying that instead of the whole `node_modules` typically takes the runner image from ~1.2GB to ~200MB, and it means a vulnerability in a build-only dependency isn't in your production image at all.

### 8.2 Compose files

`docker-compose.yml` (dev) and `docker-compose.prod.yml` share the same service list — `db`, `redis`, `backend`, `frontend`, `celery`, `celery-beat`, and optionally `flower` — but differ in what matters:

| | dev (`docker-compose.yml`) | prod (`docker-compose.prod.yml`) |
|---|---|---|
| Build | `Dockerfile` | `Dockerfile.prod` |
| Source | bind-mounted (`./backend:/app`) | baked into the image, no mount |
| Ports | exposed on all interfaces | bound to `127.0.0.1:<port>` — nginx fronts public traffic |
| `backend` command | image `CMD` (migrate + runserver) | image `CMD` (`uvicorn`, no migrate) |
| Dev extras | `debug-toolbar`, `flower`, mailhog | none |
| Resource limits | none | `deploy.resources.limits` per service |
| Log rotation | default | `max-size` / `max-file` per service |
| `restart` | `unless-stopped` | `unless-stopped` |

**Every service that another service depends on for correctness gets a real healthcheck**, and dependents use `condition: service_healthy`, so `celery` never starts racing a `backend` that hasn't booted. The original version of this scaffold only health-checked `backend`; that leaves a stuck Celery worker or a crashed Next.js server invisible, which is exactly the failure that wakes you up at 3am. All four:

```yaml
services:
  db:
    image: postgres:17-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    container_name: ${PROJECT_NAME}_backend
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz/"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }

  celery:
    container_name: ${PROJECT_NAME}_celery
    command: ["celery", "-A", "config", "worker", "-l", "info", "--concurrency", "4"]
    healthcheck:
      test: ["CMD-SHELL", "celery -A config inspect ping -d celery@$$HOSTNAME || exit 1"]
      interval: 60s
      timeout: 20s
      retries: 3
      start_period: 60s
    depends_on:
      backend: { condition: service_healthy }

  celery-beat:
    container_name: ${PROJECT_NAME}_celery_beat
    command: ["celery", "-A", "config", "beat", "-l", "info",
              "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler"]
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/celerybeat.pid && kill -0 $$(cat /tmp/celerybeat.pid)"]
      interval: 60s
      timeout: 10s
      retries: 3
    depends_on:
      backend: { condition: service_healthy }

  frontend:
    container_name: ${PROJECT_NAME}_frontend
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider",
             "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

`/healthz/` (in `config/views.py`) should check the things whose failure means "don't send traffic here" — a `SELECT 1` against the DB and a Redis `ping` — and return 503 if either fails. A healthcheck that only proves Python is running will happily report healthy while every request 500s. Keep it unauthenticated, excluded from throttling, and out of the Sentry transaction sample.

Production-only hardening, per service:

```yaml
  backend:
    deploy:
      resources:
        limits: { cpus: "2.0", memory: 2G }
        reservations: { memory: 512M }
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "5" }
    security_opt: ["no-new-privileges:true"]
    read_only: false      # Django needs /tmp and staticfiles; use tmpfs if you want true RO
```

Without resource limits a runaway container starves everything else on a shared VPS; without log rotation a long-running prod container fills the disk, and a full disk takes Postgres down with it. Both are three lines and both are the kind of thing nobody adds until after it happens once.

**Container names come from the root `.env`'s `PROJECT_NAME`** (`container_name: ${PROJECT_NAME}_backend`) rather than being hardcoded — that's what keeps this scaffold copy-paste-safe across projects, and it's what `deploy-prod.sh`'s health-check loop (§9) references directly.

Use compose **profiles** for optional dev services (`flower`, `mailhog`, `debug-toolbar` sidecars) so `docker compose up` stays lean and `docker compose --profile tooling up` brings the extras.

## 9. Deployment

Deployment is push-based, not a `git pull` on the server — `deploy-prod.sh` rsyncs the working tree to the target server, then runs the rebuild/rollout remotely over SSH. Configuration for *where* to deploy lives in `deploy/deploy.prod.env` (gitignored; `deploy.prod.env.example` is the tracked template), not in the script:

```bash
# deploy/deploy.prod.env
SERVER_HOST=
SERVER_USER=
SERVER_PATH=/opt/my-client-project
SSH_PORT=22
SSH_KEY_PATH=
```

`deploy-prod.sh`, run from the repo root, does — in order:

1. **Validate** `deploy.prod.env` exists with `SERVER_HOST`/`SERVER_USER` set; confirm it's being run from the repo root (checks for `docker-compose.prod.yml`); confirm the working tree is clean and, ideally, that CI is green on this commit — deploying a dirty tree is how "it works on my machine" reaches production literally.
2. **Rsync** the working tree, excluding everything that shouldn't travel: `.git`, `.idea`/`.vscode`, `**/__pycache__`, `**/.venv`, `**/node_modules`, `**/.next`, `media/`, and any `.env`/`.env.prod` (those live only on the server).
3. **On the server, over SSH:** confirm every required `.env.prod` file exists (root, `backend/`, `frontend/`) and fail loudly rather than deploying with a missing config; then `docker compose -f docker-compose.prod.yml --env-file .env.prod build --pull` and `up -d --remove-orphans`.
4. **Wait for the backend healthcheck** to report healthy (poll `docker inspect`, bounded retries — fail and dump the last 100 log lines rather than hanging forever).
5. **Only once healthy:** run `migrate` and `collectstatic --noinput` via `docker compose exec` — deliberately *not* in the container's boot command, so a migration runs once per deploy rather than once per replica or restart.
6. **Verify** every expected container is actually `running` (not just that `up -d` returned success) and, now that everything has a healthcheck (§8.2), that each is `healthy` — dump logs for anything that isn't.
7. **Reload nginx** if present, after `nginx -t` passes.
8. **`--follow`** optionally tails `docker compose logs -f` after a successful deploy.

Two additions worth making to the original design:

- **`--backup-db` (or unconditional).** Take a `pg_dump` on the server before step 5 runs a migration. A destructive migration with no backup is the one failure mode in this list you cannot recover from, and it costs one line.
- **A note on migration ordering.** Steps 3–5 mean the new code is serving traffic *before* migrations run, which is fine for additive migrations and dangerous for destructive ones. For a single-container deploy the practical rule is: make migrations backward-compatible (add columns nullable, deploy, backfill, then drop in a later release) so there's never a window where running code and the schema disagree. Say this out loud in the script's header comment, because it's the kind of thing that's obvious in principle and forgotten under deadline.

Failing loudly and early (missing env file, unhealthy container, failed nginx test, dirty tree) matters more here than anywhere else in this scaffold — a deploy script's whole job is to be the thing that stops a bad rollout, not the thing that quietly ships one.

## 10. Bootstrapping & Setup Walkthrough

```bash
# 1. Clone the scaffold — frontend/ and backend/ come together, already wired
git clone https://github.com/yourorg/base-scaffold.git my-client-project
cd my-client-project

# 2. Detach from the scaffold's history — from here on, this is just your code
rm -rf .git && git init

# 3. Name the project (drives container names, DB name, and CLAUDE.md's header)
./scripts/rename-project.sh my-client-project     # see §11

# 4. Environment
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
python3 -c "import secrets; print(secrets.token_urlsafe(64))"                    # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
# paste both into backend/.env, then fill in DB creds and PROJECT_NAME

# 5. Python + Node dependencies
cd backend && uv sync && cd ..
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

At this point the project is fully independent. Installing a reusable app package (both halves) follows the protocol in `INTEGRATION-GUIDE.md` §2, and there's no further contact with the base-scaffold repo unless you're deliberately backporting an improvement by hand.

### 10.1 `CLAUDE.md` is generated, not copied blank

Step 3's `rename-project.sh` fills the project name into `CLAUDE.md` from the template (see `CLAUDE.md.template`). Keeping it generated rather than hand-written matters because a `CLAUDE.md` with the wrong project name and a stale installed-apps list is worse than none — an agent will trust it.

### 10.2 `Makefile`

```make
.DEFAULT_GOAL := help
.PHONY: help up down logs shell test lint fmt typecheck migrate migrations superuser \
        install check deploy

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

up:            ## Start the dev stack
	docker compose up --build
down:          ## Stop the dev stack
	docker compose down
logs:          ## Tail all logs
	docker compose logs -f
shell:         ## Django shell_plus in the backend container
	docker compose exec backend python manage.py shell_plus
migrate:       ## Apply migrations
	docker compose exec backend python manage.py migrate
migrations:    ## Create migrations
	docker compose exec backend python manage.py makemigrations
superuser:     ## Create a superuser
	docker compose exec backend python manage.py createsuperuser
test:          ## Run the host test suite against an ephemeral Postgres + Redis
	docker compose -f docker-compose.test.yml up -d --wait
	cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow"
	docker compose -f docker-compose.test.yml down
lint:          ## Ruff + ESLint
	cd backend && uv run ruff check .
	cd frontend && npm run lint
fmt:           ## Format everything
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
typecheck:     ## mypy + tsc
	cd backend && uv run mypy .
	cd frontend && npx tsc --noEmit
check: lint typecheck test  ## Everything CI runs, locally
deploy:        ## Deploy to production
	./deploy/deploy-prod.sh
```

The `check` target is the one that matters: it gives `CLAUDE.md` a single command to name as the definition of done, and it gives a human one command to run before pushing.

## 11. Ecosystem Tooling

Three small pieces of tooling that live *outside* any single project and make the whole ecosystem cheaper to operate. None is strictly necessary on day one; all three pay for themselves by the third project.

### 11.1 `scripts/rename-project.sh` (in the scaffold)

Replaces the placeholder project name across `.env.example`, `docker-compose*.yml`, `CLAUDE.md`, `pyproject.toml`, and `package.json` in one pass. Hand-editing these is a five-minute job that gets done wrong roughly every other time, and the failure mode (two projects sharing a `PROJECT_NAME`, so their containers collide) is confusing to diagnose.

### 11.2 `create-app-package` (a separate template repo)

`BASE-DESIGN.md` solves "starting a new project" well. Starting a new *app package* still means hand-building the whole `APP-DESIGN.md` §2 skeleton — the dual-package layout, the README config-block stub, the CI caller workflow, the playground, the pytest settings module. That's exactly the repetitive setup this ecosystem exists to eliminate.

Use `copier` (preferred — it supports updating a generated project when the template improves, which matters as the standard evolves) or a plain `degit`-style template repo plus a script. It prompts for: package name, importable module name, whether it has a frontend half, and the initial `.env`/settings keys, then emits a repo that already passes CI with zero code in it. The first app you generate this way will feel like overkill; the fourth will not.

### 11.3 An app registry

Once there are more than a handful of app packages, "what already exists that I could reuse here?" has no answer in the current design — and reuse across projects is the entire point of the architecture. A single `APPS.md` (or `apps.json`, if you want tooling to read it) in an org-level meta-repo, listing every app with its latest tag, a one-line description, and its required host settings:

```markdown
| App | Latest | Purpose | Notes |
|---|---|---|---|
| `auth-app` | v3.1.0 | JWT auth, registration, password reset | Every project needs this first |
| `notifications-app` | v1.4.2 | Email/SMS/push delivery + templates | Extras: `[sms]`, `[push]` |
| `payments-app` | v2.1.0 | Stripe charges, refunds, webhooks | Requires `notifications-app` wiring in `core/` |
| `ticketing-app` | v0.4.0 | Support tickets, categories, SLA timers | Uses `contenttypes` for optional links |
```

Keep it updated as the last step of each app's release workflow. It's also the single most useful file to paste into an agent's context when starting a new project, because it turns "build a notification system" into "install the one that already exists."
