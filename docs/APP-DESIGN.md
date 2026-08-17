# APP-DESIGN.md — Reusable App Package Architecture

> **Companion documents:** `BASE-DESIGN.md` (the host scaffold), `INTEGRATION-GUIDE.md` (how a host wires apps in), `CLAUDE-CODE-GUIDE-APP.md` (how to actually build one of these with an AI agent).

## Table of contents

1. [Purpose & Package Contract](#1-purpose--package-contract)
2. [Package Folder Structure](#2-package-folder-structure)
3. [Toolchain, Dependencies & Project Configuration](#3-toolchain-dependencies--project-configuration)
4. [Views, Rate Limiting & API Documentation Standards](#4-views-rate-limiting--api-documentation-standards)
5. [Two Admin Surfaces & Permissions](#5-two-admin-surfaces--permissions)
6. [Inter-App Communication (Signals & Services)](#6-inter-app-communication-signals--services)
7. [Testing Standards](#7-testing-standards)
8. [Documentation Standard (`README.md` Contract)](#8-documentation-standard-readmemd-contract)
9. [Security Checklist](#9-security-checklist)
10. [Continuous Integration](#10-continuous-integration)
11. [Release Workflow](#11-release-workflow)
12. [Frontend SDK Contract](#12-frontend-sdk-contract)

---

## 1. Purpose & Package Contract

A reusable app is a **standalone, versioned Python package** — its own GitHub repo, its own release history, installable into any host project via `uv`. Once installed, it lives in `.venv/lib/.../site-packages` as read-only, third-party code: nothing inside it is ever hand-edited from within a host project. If a host project needs different behavior, that's a new version of the package, or a project-level override/subclass in the host's `core/` layer (see `INTEGRATION-GUIDE.md`) — never a local edit to the installed files.

**Versioning:** every release is tagged `vX.Y.Z` (semantic versioning — breaking changes bump major, additive/back-compatible features bump minor, fixes bump patch). A host project pins the exact tag it depends on:

```bash
uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"
```

`uv` records that in the host's `pyproject.toml` and resolves the exact commit hash into the host's `uv.lock`, so `uv sync` reproduces the identical tree on any machine and in CI. Upgrading is changing that one pinned ref and re-syncing — never assume a host project is on the latest version, and never publish a breaking change under a minor/patch bump.

**Full-stack packages.** Every reusable app is a **dual-package monorepo**: a Python/Django half installed into the backend, and a TypeScript/React half installed into the frontend (see §12). Both halves live in the same repo and release under the *same* version tag, so a host is never stuck pairing an old hook against a new API shape or vice versa — see §11 for how a release keeps both in lockstep, and §10 for the CI job that makes a version mismatch fail the build rather than ship.

### 1.1 Dependency declaration rules — permissive ranges, never exact pins

This is the single most important rule in this document that has nothing to do with code structure, because getting it wrong makes apps *un-combinable*.

When a host installs three app packages, `uv` resolves **one shared environment** across the host's own dependencies and every installed app's dependencies. There is no per-app isolation — they all share one `site-packages`. So if `payments-app` declares `djangorestframework==3.15.0` and `notifications-app` declares `djangorestframework==3.14.2`, that combination is *unresolvable*, and it surfaces as an opaque resolver error at `uv add` time in some unlucky host project six months from now.

Therefore:

- **Shared platform dependencies get wide ranges.** `django`, `djangorestframework`, `celery`, `redis`, `drf-spectacular`, `python-decouple`, `django-celery-beat` — anything the host also depends on directly — are declared as compatible ranges with an upper bound at the next known-breaking major:
  ```toml
  dependencies = [
      "django>=5.2,<7.0",
      "djangorestframework>=3.15,<4.0",
      "drf-spectacular>=0.27,<1.0",
  ]
  ```
- **App-private dependencies can be tighter**, but still prefer a range. A niche library only this app uses (`stripe`, `twilio`, `qrcode`) is less likely to collide, so `"stripe>=11,<13"` is fine — but `==` is still discouraged, because the moment a second app also needs `stripe`, an exact pin on both sides is a coin flip.
- **The host pins the exact versions everyone runs against.** The host's `pyproject.toml` + `uv.lock` is where `django==6.0.4` actually gets decided. Apps declare what they *tolerate*; the host decides what *runs*.
- **Never declare a dependency on another app package.** Not even a loose range. See §6.
- **Test/lint tooling never appears in `dependencies`.** It goes in `[dependency-groups]`, which is never installed by a consumer — see §3.

### 1.2 Private repository access

`git+https://github.com/yourorg/...` implies a private org repo in most real setups. Two supported ways to authenticate, both documented so a host (or a CI job, or a Docker build) never has to guess:

- **SSH:** use `git+ssh://git@github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend` and rely on the developer's SSH agent. In Docker, forward the agent with `RUN --mount=type=ssh`.
- **Token:** set `UV_INDEX_...`/`GIT_CONFIG` credential helpers, or in CI export a `GH_TOKEN` and configure `git config --global url."https://x-access-token:${GH_TOKEN}@github.com/".insteadOf "https://github.com/"`. In Docker use `RUN --mount=type=secret,id=gh_token`.

**Never pass a token as a Docker `ARG` or `ENV`.** It persists in image history even if a later layer unsets it.

### 1.3 Namespacing convention

A handful of things from every installed app end up merged into one shared, flat namespace — one `settings.py`, one `.env`, one React Query cache. Two apps picking the same short name silently collide there, so every one of these is prefixed with the app's own name, no exceptions:

- **Throttle scopes** — `notifications_list`, not `list` (§4).
- **Settings dict keys** — `NOTIFICATIONS = {...}`, not `SETTINGS = {...}` (§3, §8).
- **`.env` keys** — `NOTIFICATIONS_PROVIDER_API_KEY`, not `PROVIDER_API_KEY` (§8).
- **Frontend query keys** — `["notifications", ...]`, not `["list", ...]` (§12).
- **Celery task names** — `notifications_app.tasks.cleanup`, which comes free if tasks live in the app's own module (don't override `name=` with something short).
- **Cache keys** — any `cache.set()` key is prefixed too; the host runs one Redis instance.

None of this is enforced by tooling — it's a convention every app package is expected to follow, and it's the first thing to check if a throttle rate or a cache invalidation is behaving strangely across two apps that were each written correctly in isolation.

## 2. Package Folder Structure

```
notifications-app/                       # the repo
├── README.md                            # ONE doc covering both halves — Python config AND
│                                          npm/hook integration, see §8
├── CHANGELOG.md                          # Keep a Changelog format, ONE changelog for the
│                                          whole package — both halves release together, §11
├── CLAUDE.md                             # agent instructions for working IN this repo,
│                                          see CLAUDE-CODE-GUIDE-APP.md
├── .python-version                       # e.g. "3.14" — matches CI and the playground image
├── .pre-commit-config.yaml               # ruff, mypy, prettier/eslint — see §3
├── .github/
│   └── workflows/
│       └── ci.yml                        # thin caller of the org reusable workflow, see §10
├── backend/
│   ├── pyproject.toml                    # build config, dependencies, dependency-groups,
│   │                                       ruff/mypy/pytest config — see §3
│   ├── uv.lock                            # committed; used by CI and the playground only —
│   │                                       NEVER travels to a consuming host, see §3.4
│   ├── MANIFEST.in                        # ships locale/, templates/, static/ in the wheel
│   └── src/
│       └── notifications_app/             # the importable package — this name is what
│           │                                goes in INSTALLED_APPS and every import
│           ├── __init__.py
│           ├── apps.py                    # AppConfig — name, verbose_name (translatable)
│           ├── conf.py                    # typed accessor over the host's NOTIFICATIONS
│           │                                settings dict, with defaults — see §3.5
│           ├── models.py                  # indexed and query-optimized, see note below
│           ├── admin.py                   # Jazzmin ModelAdmin registrations, see §5
│           ├── admin_views.py             # custom admin-dashboard API views, see §5
│           ├── views.py                   # user-facing API views
│           ├── serializers.py
│           ├── permissions.py             # user-facing + IsAppAdmin, see §5
│           ├── signals.py                 # emits this app's own events, see §6
│           ├── services.py                # its public callable interface, see §6
│           ├── urls.py                    # user-facing endpoints
│           ├── urls_admin.py              # admin-dashboard endpoints
│           ├── tasks.py                   # celery / django.tasks — autodiscovered by host
│           ├── utils.py                   # bundled cache/mixin helpers, see §4
│           ├── factories.py               # factory_boy factories — PUBLIC test surface, §7.3
│           ├── migrations/
│           ├── locale/                    # translations, bundled via package data, see §8
│           └── templates/notifications_app/   # namespaced so a host can override
│                                                cleanly, see INTEGRATION-GUIDE.md §5
├── frontend/
│   ├── package.json                       # name, peer deps, build config, see §12
│   ├── tsconfig.json                      # "strict": true, no exceptions
│   ├── vitest.config.ts
│   └── src/
│       ├── index.ts                       # the ONLY entrypoint a host imports from, §12
│       ├── hooks/
│       │   ├── useNotifications.ts
│       │   └── useSendNotification.ts
│       ├── api/
│       │   ├── client.ts                  # low-level shared HTTP client, see §12
│       │   └── manager.ts                 # typed NotificationsManager — the ONLY place
│       │                                    raw requests happen, see §12
│       └── types.ts
├── playground/                            # local dev host — a minimal Django+Next pair with
│   │                                        both halves linked by path, see §11.2
│   ├── backend/
│   ├── frontend/
│   └── docker-compose.yml
└── tests/
    ├── backend/                           # pytest — authoritative gate for the Python half
    │   ├── conftest.py
    │   └── test_*.py
    └── frontend/                          # Vitest + MSW — authoritative gate for the TS half
```

Two structural notes that cause the most first-time breakage:

**Package data must be declared, or it silently doesn't ship.** `locale/`, `templates/`, and any `static/` are not `.py` files, so no build backend includes them by default. With `setuptools` that means `include-package-data = true` in `pyproject.toml` plus a matching `MANIFEST.in`; with `hatchling` it means an explicit `[tool.hatch.build.targets.wheel]` include list. Skipping this is the most common reason a freshly-installed app "loses" its translations or templates — and §10's wheel-smoke-test CI job exists specifically to catch it before a release.

**Indexes and query optimization are baseline, not per-app.** Every model in `models.py` declares `Meta.indexes` for fields used in frequent filters, ordering, or foreign key lookups, and every queryset in `views.py`/`services.py` uses `select_related`/`prefetch_related` to avoid N+1 queries.

### Referencing the host's user model

Nearly every app needs a `user` field, but auth is its own separate installed package — an app can't `import` it without violating the no-inter-app-imports rule (§6). Django already has the sanctioned indirection for exactly this: reference `settings.AUTH_USER_MODEL`, never a specific User model:

```python
# notifications_app/models.py
from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]
```

```python
# notifications_app/migrations/0001_initial.py (excerpt)
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [...]
```

This isn't an import of the auth package — it's a string reference Django resolves at runtime, and `swappable_dependency` is what makes the migration graph run the auth app's migrations first automatically, regardless of which specific auth package a host has installed. This is the *only* app-to-app reference every app is expected to need; see §6 for what to do on the rarer occasions an app needs to reference something else entirely.

## 3. Toolchain, Dependencies & Project Configuration

`uv` is the only Python package manager in this ecosystem. There is no `requirements.txt` anywhere, in an app or in a host — one dependency declaration format, one lockfile format, one install command.

### 3.1 `backend/pyproject.toml` — the canonical file

```toml
[build-system]
requires = ["setuptools>=77", "setuptools-scm>=8"]
build-backend = "setuptools.build_meta"

[project]
name = "notifications-app"
version = "1.4.2"                    # kept in lockstep with CHANGELOG.md + package.json, §11
description = "Multi-channel notification delivery for Django, as an installable app package."
requires-python = ">=3.13"           # a RANGE, not a pin — a host may be on 3.13 or 3.14
license = "MIT"
readme = "../README.md"

# Wide ranges on anything the host also depends on — see §1.1
dependencies = [
    "django>=5.2,<7.0",
    "djangorestframework>=3.15,<4.0",
    "drf-spectacular>=0.27,<1.0",
    "python-decouple>=3.8,<4.0",
]

[project.optional-dependencies]
# Extras = features a CONSUMER opts into. Installed with notifications-app[sms].
sms = ["twilio>=9,<10"]
push = ["pyfcm>=2,<3"]

[dependency-groups]
# PEP 735 groups = tooling for developing THIS package. Never installed by a consumer,
# never published, not visible to a host at all. This is the correct home for all of it.
dev = [
    "ruff>=0.12",
    "mypy>=1.14",
    "django-stubs[compatible-mypy]>=5.1",
    "djangorestframework-stubs>=3.15",
    "pre-commit>=4.0",
]
test = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "pytest-cov>=6.0",
    "pytest-xdist>=3.6",
    "factory-boy>=3.3",
    "psycopg[binary]>=3.2",          # tests run on Postgres, see §7.5
]

[tool.uv]
default-groups = ["dev", "test"]     # `uv sync` gives a contributor everything

[tool.setuptools]
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

# ---------------------------------------------------------------- ruff
[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "../tests"]

[tool.ruff.lint]
select = [
    "E", "W",     # pycodestyle
    "F",          # pyflakes
    "I",          # isort
    "UP",         # pyupgrade
    "B",          # bugbear
    "DJ",         # flake8-django
    "S",          # bandit — security
    "TID",        # tidy-imports (used to enforce §6, see below)
    "RUF",
]
ignore = ["S101"]  # assert is fine in tests

[tool.ruff.lint.per-file-ignores]
"../tests/**" = ["S", "TID251"]
"*/migrations/*" = ["E501", "RUF012"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

# Machine-enforced version of the §6 rule: this package may not import a sibling app.
# Add a line per app that exists in the ecosystem; the CI job in §10 also greps as a backstop.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"payments_app".msg = "App packages must never import each other — see APP-DESIGN.md §6."
"cart_app".msg = "App packages must never import each other — see APP-DESIGN.md §6."
"auth_app".msg = "Use settings.AUTH_USER_MODEL instead — see APP-DESIGN.md §2."

# ---------------------------------------------------------------- mypy
[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["mypy_django_plugin.main", "mypy_drf_plugin.main"]
warn_unreachable = true
exclude = ["migrations/"]

[[tool.mypy.overrides]]
module = "*.migrations.*"
ignore_errors = true

[tool.django-stubs]
django_settings_module = "tests.backend.settings"

# ---------------------------------------------------------------- pytest (see §7)
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "tests.backend.settings"
pythonpath = ["src", ".."]
testpaths = ["../tests/backend"]
python_files = ["test_*.py"]
addopts = """
  -ra --strict-markers --strict-config
  --cov=notifications_app --cov-report=term-missing --cov-fail-under=85
"""
markers = [
    "slow: excluded from the default run, opt in with -m slow",
    "integration: crosses a real DB/broker boundary rather than mocking it",
]
filterwarnings = ["error::DeprecationWarning"]

[tool.coverage.run]
omit = ["*/migrations/*", "*/tests/*"]
```

### 3.2 Everyday commands

```bash
uv sync                       # create .venv, install deps + dev + test groups
uv run pytest                 # run the suite in that env, no manual activation
uv run ruff check --fix .
uv run ruff format .
uv run mypy src
uv add "stripe>=11,<13"       # adds to [project.dependencies] and re-locks
uv add --group test "freezegun>=1.5"
uv lock --upgrade-package django   # move one dep within its declared range
uv build                      # produce the wheel + sdist CI smoke-tests in §10
```

### 3.3 `.python-version` and interpreter policy

Commit a `.python-version` containing the version CI and the playground use (e.g. `3.14`). It pins what `uv` provisions locally; `requires-python` in `pyproject.toml` stays a *range*, because that's a compatibility claim to consumers, not a local preference. Keeping these two conceptually separate avoids the trap of accidentally telling every host "you must be on exactly 3.14."

### 3.4 The lockfile boundary — the most common `uv` misconception

**An app package's `uv.lock` never travels downstream.** When a host runs `uv add "git+...#subdirectory=backend"`, `uv` reads only that package's `pyproject.toml` `[project.dependencies]`. The app's own lockfile is used for exactly two things: reproducing a contributor's dev environment, and pinning CI. This is why §1.1's range rule matters so much — the ranges *are* the published contract, and a green CI run against your locked versions proves nothing about what a host will resolve. §10 includes a `resolution-matrix` job that resolves against the *lowest* and *highest* ends of your declared ranges precisely to close that gap.

### 3.5 Settings access — `conf.py`, not scattered `getattr` calls

An app reads host configuration from one place, with defaults, so a host that omits an optional key gets a sane value instead of an `AttributeError` deep in a view:

```python
# notifications_app/conf.py
from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    "DEFAULT_CHANNEL": "email",
    "RETENTION_DAYS": 90,
    "MAX_BATCH_SIZE": 500,
}


def get_setting(key: str) -> Any:
    """Read a NOTIFICATIONS setting, falling back to this app's documented default."""
    return getattr(settings, "NOTIFICATIONS", {}).get(key, DEFAULTS[key])
```

Required-and-secret values (API keys) are the exception: those come from the environment via `decouple.config("NOTIFICATIONS_PROVIDER_API_KEY")` and should fail loudly at import or first use if missing, rather than defaulting. Every key in `DEFAULTS` and every `.env` key is listed in the README block (§8) — that file and this one must agree, and §11 makes updating them a release step.

### 3.6 Pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.12.0
    hooks:
      - id: ruff
        args: [--fix]
        files: ^backend/
      - id: ruff-format
        files: ^backend/
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
        files: ^backend/src/
        additional_dependencies: [django-stubs, djangorestframework-stubs]
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: ^frontend/
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-merge-conflict
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
```

`uv run pre-commit install` once per clone. This matters more in this ecosystem than in a normal project: you have one base repo plus N app repos that all need to stay stylistically consistent without a human re-checking each one, and pre-commit is what makes that automatic instead of aspirational.

## 4. Views, Rate Limiting & API Documentation Standards

- **Caching & error handling.** Every GET/list/retrieve view uses a caching mixin, and every view uses consistent error-handling/response conventions. Because this package must work standalone in *any* host project, it cannot import a host's `backend/tools/` — that folder is project-owned and isn't guaranteed to exist, or to exist at a stable import path, in every host. Instead, bundle a small internal equivalent (`notifications_app/utils.py`) with the same shape as the scaffold's `tools/cache.py` / `tools/mixins.py`, so the code reads the same way whether you're in an app package or in a host's `core/` layer. If duplication across several apps starts to hurt, the follow-up is a small shared toolkit package every app depends on explicitly in `pyproject.toml` — an explicit dependency declaration, never an assumption about the host's internals.
- **Rate limiting.** Every view declares a `throttle_scope`, prefixed per §1.3, and every scope is listed in the app's `README.md` (§8) so a host knows what to add to `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`. No view ships without one.
- **API documentation.** Every view/viewset carries a complete `drf-spectacular` `@extend_schema` (or `extend_schema_view`) — summary, description, request/response serializers, and `tags=["notifications"]` for public views or `tags=["notifications-admin"]` for admin-dashboard views, so Swagger stays grouped per app and per surface.
- **Pagination.** List views that can return unbounded data set an explicit `pagination_class` rather than relying on the host's `DEFAULT_PAGINATION_CLASS`, which the app can't know. The page-size default is documented in the README block.

```python
# notifications_app/views.py — every view in every app should structurally match this
# shape: bundled caching mixin, throttle_scope, full schema, a real permission class,
# and an optimized queryset.
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from .models import Notification
from .permissions import IsNotificationOwner
from .serializers import NotificationSerializer
from .utils import CachedListMixin   # this app's own bundled cache helper, per above


@extend_schema(
    summary="List the current user's notifications",
    description="Returns notifications belonging to the authenticated user, newest first.",
    responses={200: NotificationSerializer(many=True)},
    tags=["notifications"],
)
class NotificationListView(CachedListMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsNotificationOwner]
    throttle_scope = "notifications_list"
    cache_timeout = 30  # seconds — CachedListMixin's own convention

    def get_queryset(self):
        return (
            Notification.objects
            .filter(user=self.request.user)
            .select_related("user")
        )
```

## 5. Two Admin Surfaces & Permissions

Every app supports two separate admin surfaces, and its own `permissions.py` gates both:

1. **Django Admin / Jazzmin** — standard `ModelAdmin` registrations in `admin.py`. Jazzmin's per-app icon/menu ordering is configured in the *host's* `JAZZMIN_SETTINGS` — an app can suggest an icon in its `README.md`, but can't register into that dict itself.
2. **Custom Admin Dashboard API** — `admin_views.py` + `urls_admin.py`, gated by `IsAppAdmin`. These are real DRF endpoints meant for a custom admin frontend, throttled and documented exactly like public views.

`permissions.py` exposes, at minimum, one user-facing permission class (app-specific business logic) and `IsAppAdmin`. Both rely only on what Django's user model already guarantees everywhere — `is_authenticated`, `is_staff`, `is_superuser`, `user.has_perm(...)` — never on models or logic from another reusable app, which is the whole point of §6.

## 6. Inter-App Communication (Signals & Services)

An app package **must never import another app package.** The only two things it exposes for production use are `signals.py` (things that happened) and `services.py` (things you can ask it to do) — plus `factories.py` as a *test-only* third surface, see §7.3. Wiring two apps together is the host project's job, done in `backend/core/` — never inside either app. See `INTEGRATION-GUIDE.md` §4 for the full host-side pattern; here's the app side of the same example:

```python
# notifications_app/signals.py
import django.dispatch

# fired whenever a notification is actually sent — sends: user_id, channel, template
notification_sent = django.dispatch.Signal()
```

```python
# notifications_app/services.py
from .models import Notification
from .signals import notification_sent


class NotificationService:
    @staticmethod
    def send(user_id: int, template: str, context: dict, channel: str = "email") -> Notification:
        notification = Notification.objects.create(
            user_id=user_id, template=template, context=context, channel=channel
        )
        # ... actually dispatch the email/SMS/push ...
        notification_sent.send(
            sender=Notification, user_id=user_id, channel=channel, template=template
        )
        return notification
```

```python
# payments_app/signals.py
import django.dispatch

# sends: payment_id, user_id, amount
payment_completed = django.dispatch.Signal()
```

Neither package above knows the other exists. `NotificationService.send(...)` is a plain, agnostic callable — it doesn't know or care who calls it. `payment_completed` is a plain event — it doesn't know or care who's listening. The connection between them lives entirely in the host's `core/signals.py`.

**Signal payloads are a versioned contract.** Removing or renaming a kwarg from a signal, or changing a `services.py` method signature, is a **major** version bump — a host's `core/signals.py` receiver breaks silently otherwise (a missing kwarg raises at dispatch time, in production, in a background task). Document every signal's payload in the README (§8) and treat that documentation as the contract.

The same discipline applies to each app's frontend half: a package's `frontend/src/hooks/` must never import from another package's frontend SDK. Combining two apps' hooks in one UI (e.g. a checkout page using both `useCart` from one package and `useCreatePayment` from another) happens in the host's own `frontend/` code, at the page or component level — never inside either SDK. See `INTEGRATION-GUIDE.md` §4 for the worked example.

### Cross-app data references

Beyond the user relation (§2), two apps needing to relate to each other's data is common — it still doesn't mean two apps get to import each other. Two more patterns, from more common to less:

1. **An optional, dynamic reference to *any* other app's object — `contenttypes`.** When an app occasionally needs to point at an object that could live in one of several other apps (or in none, depending on the project), use Django's built-in `contenttypes` framework instead of a real foreign key:
   ```python
   # ticketing_app/models.py
   from django.contrib.contenttypes.fields import GenericForeignKey
   from django.contrib.contenttypes.models import ContentType
   from django.db import models


   class Ticket(models.Model):
       category = models.CharField(max_length=100)
       related_content_type = models.ForeignKey(
           ContentType, null=True, blank=True, on_delete=models.SET_NULL
       )
       related_object_id = models.PositiveIntegerField(null=True, blank=True)
       related_object = GenericForeignKey("related_content_type", "related_object_id")
   ```
   `contenttypes` ships with Django — it's already a dependency of `django.contrib.admin`, so it's always available — and it lets `Ticket` point at a `Payment`, an `Order`, or nothing at all, without ever importing `payments_app`. Resolving `related_object` into something meaningful is `core/`'s job, same as every other cross-app connection in this document. In practice this should be the exception, not the default — most apps, like a ticketing system that's really just a category and a status, don't need to reference anything outside themselves at all.

2. **Two concepts that are really one thing — don't force a split.** If two concepts are coupled tightly enough that they'd always need a direct reference to each other and would always release together — a cart and the order it becomes — that's a sign they're one package, not two decoupled ones with a manufactured exception carved into the import rule. Shipping them as a single package (with real foreign keys between their models, since they're in the same app) is more honest than inventing a special case for one pair of apps.

## 7. Testing Standards

`pytest` is the authoritative gate for the Python half; Vitest + MSW for the TypeScript half. Configuration lives in `backend/pyproject.toml` (§3.1) — there is no separate `pytest.ini`, `setup.cfg`, or `tox.ini`.

### 7.1 Test settings module

Tests need a real Django settings module. It lives in the test tree, not the package (the package must never contain a settings file — that's a host concern):

```python
# tests/backend/settings.py
SECRET_KEY = "test-only-not-a-secret"
DEBUG = False
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "notifications_app",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_notifications",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",   # overridden to "postgres" by CI env, see §10
        "PORT": "5432",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "notifications_list": "60/min",
        "notifications_send": "20/min",
    },
}

NOTIFICATIONS = {"DEFAULT_CHANNEL": "email"}
```

Keeping this minimal is deliberate: if your tests only pass with fifteen extra apps installed, the package has an undeclared dependency on a host's configuration, and a real host will hit that.

### 7.2 `conftest.py` hierarchy

```
tests/backend/conftest.py          # app-wide fixtures: api_client, user, admin_user
tests/backend/api/conftest.py      # fixtures only the view tests need
```

```python
# tests/backend/conftest.py
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from notifications_app.factories import NotificationFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="alice", password="pw")


@pytest.fixture
def auth_client(api_client, user) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def notification(user):
    return NotificationFactory(user=user)
```

In a **host** project the same hierarchy applies, one level up: `backend/conftest.py` for project-wide fixtures, `backend/core/tests/conftest.py` for anything spanning apps. See `INTEGRATION-GUIDE.md` §4.

### 7.3 `factories.py` — the third public surface

This is a deliberate addition to the two-surface rule in §6, and it solves a real problem: a host's `core/tests/test_signals.py` needs to construct a realistic `Payment` in order to fire `payment_completed` at it. Without a sanctioned way to do that, every host either duplicates the app's creation logic or reaches directly into its models — both worse than the alternative.

So: **every app ships `factories.py` inside the package** (not in `tests/`, so it's importable from a host), and it is an explicitly public, importable surface for **test code only**:

```python
# notifications_app/factories.py
import factory
from django.contrib.auth import get_user_model

from .models import Notification


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    template = "welcome"
    channel = "email"
    context = factory.Dict({})
```

Rules for it:
- `factory-boy` is declared in the `test` **dependency group**, not `[project.dependencies]` — so a host that imports factories in its tests must add `factory-boy` to its own test group. Document that in the README block. (An app must not force `factory-boy` into every production install.)
- Importing `notifications_app.factories` from another app's *tests* or from `core/tests/` is allowed and expected. Importing it from anywhere in production code is a bug, and `ruff`'s `TID251` config in §3.1 should ban it outside test paths.
- Factories are covered by semver like anything else public: renaming `NotificationFactory` is a breaking change.

### 7.4 What gets tested, at minimum

An app's suite isn't complete until it covers:

| Area | Minimum bar |
|---|---|
| Every `services.py` method | Happy path + at least one failure path |
| Every view | 200 for the permitted user, 403 for another user's object (the IDOR case from §9), 401 unauthenticated |
| Every signal it emits | Fired with the exact documented payload — connect a receiver in the test and assert kwargs |
| Every serializer | Write-path validation rejects bad input; read-path omits sensitive fields |
| Every `tasks.py` task | Called synchronously as a plain function (`CELERY_TASK_ALWAYS_EAGER` is not needed if you call `task_fn(...)` directly) |
| Throttling | One test asserting the scope name exists and is applied — a typo'd `throttle_scope` fails open, silently |
| Migrations | `pytest --create-db` proves they apply cleanly from zero; a `makemigrations --check --dry-run` step in CI proves none are missing |

### 7.5 Postgres, not SQLite

Tests run against real Postgres, locally and in CI. SQLite papers over behavioral differences that only surface in production — `JSONField` lookups, `select_for_update`, `ArrayField`, case-sensitivity in `iexact`, constraint deferral, and transaction semantics. `playground/docker-compose.yml` provides a Postgres for local runs; §10's CI job provides one as a service container. The connection host comes from an env var so the same config works in both.

### 7.6 Markers, coverage, parallelism

- `-m "not slow"` is the default developer loop; CI runs everything.
- `integration` marks anything touching a real DB/broker rather than a mock — useful for running the fast half first in a pre-push hook.
- `--cov-fail-under=85` is enforced in CI, not eyeballed. Pick a number you'll actually hold; a threshold you routinely lower is worse than none.
- `-n auto` (`pytest-xdist`) once the suite passes a few seconds. Note it requires tests to be independent — a shared-state test that only passes serially is a bug worth finding early.

### 7.7 Frontend testing

Vitest + MSW (Mock Service Worker) is the standard — mock the HTTP layer, never a live backend, so the test suite runs the same in CI as it does locally:

```tsx
// tests/frontend/useSendNotification.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useSendNotification } from "../../frontend/src/hooks/useSendNotification";

const server = setupServer(
  http.post("/api/v1/notifications/send/", () =>
    HttpResponse.json({ id: "1", status: "sent" })
  )
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

test("sends a notification and returns the created record", async () => {
  const { result } = renderHook(() => useSendNotification(), { wrapper });
  result.current.mutate({ userId: "42", template: "welcome" });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual({ id: "1", status: "sent" });
});
```

Two details that matter: `onUnhandledRequest: "error"` turns a hook accidentally calling an undeclared endpoint into a test failure instead of a silent hang, and `retry: false` stops react-query's default retry from making a failure-path test take three seconds. Every hook gets at least one success-path test and one error-path test (mock a 4xx/5xx and assert `isError`) — a hook without an error-path test is the frontend equivalent of a backend view no one checked against a failed permission.

## 8. Documentation Standard (`README.md` Contract)

Every app's `README.md` must include a **copy-paste-ready configuration block** so wiring the app into a host project is mechanical, not exploratory. At minimum:

````markdown
## Installation — backend

```bash
uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"
```

Optional extras: `notifications-app[sms]` adds Twilio support, `[push]` adds FCM.

## Compatibility

- Python 3.13+ · Django 5.2–6.x · DRF 3.15+
- Requires `django.contrib.contenttypes` (present by default with the admin).

## Settings — add to `backend/config/settings.py`

```python
INSTALLED_APPS += ["notifications_app"]

MIDDLEWARE += []  # none required

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({
    "notifications_list": "60/min",
    "notifications_send": "20/min",
})

NOTIFICATIONS = {
    "DEFAULT_CHANNEL": "email",   # "email" | "sms" | "push"
    "RETENTION_DAYS": 90,
    "MAX_BATCH_SIZE": 500,
}
```

## Required `.env` keys

```
NOTIFICATIONS_PROVIDER_API_KEY=      # required — the app fails at startup without it
NOTIFICATIONS_FROM_ADDRESS=          # optional, defaults to DEFAULT_FROM_EMAIL
```

## URL mounting — add to `backend/config/urls.py`

```python
path("api/v1/notifications/", include("notifications_app.urls")),
path("api/v1/admin/notifications/", include("notifications_app.urls_admin")),
```

## Migrations

```bash
uv run python manage.py migrate notifications_app
```

## Signals emitted (contract — payload changes are a MAJOR bump)

| Signal | Payload kwargs |
|---|---|
| `notification_sent` | `user_id: int`, `channel: str`, `template: str` |
| `notification_failed` | `user_id: int`, `channel: str`, `error: str` |

## Services (public callables)

| Method | Signature |
|---|---|
| `NotificationService.send` | `(user_id: int, template: str, context: dict, channel: str = "email") -> Notification` |

## Test helpers

`notifications_app.factories` exports `NotificationFactory` and `UserFactory` for host
tests. Add `factory-boy` to your own test dependency group to use them.

## Recommended periodic schedule (optional)

```
notifications_cleanup — daily at 03:00 — notifications_app.tasks.cleanup_old_notifications
```

This is a recommendation, not something that auto-registers — the host creates the actual
`django_celery_beat` schedule entry, see `BASE-DESIGN.md` §6.

## Suggested Jazzmin icon

`fas fa-bell` — add under `JAZZMIN_SETTINGS["icons"]["notifications_app.Notification"]`.

## Installation — frontend

```bash
npm install "github:yourorg/notifications-app#v1.4.2:frontend"
```

## Usage — import hooks from the package root

```tsx
import { useNotifications, useSendNotification } from "notifications-app";

function NotificationBell() {
  const { data: notifications } = useNotifications();
  const { mutate: send } = useSendNotification();
  // ...
}
```

Requires the host's `@tanstack/react-query` `QueryClientProvider` to already be mounted
(it is, by default, in the scaffold's `frontend/lib/query-client.ts` — see
`BASE-DESIGN.md` §3). No further frontend configuration needed.
````

An app that ships without every one of these sections isn't done — see §11's release checklist, and §10's CI job that fails when the README's declared throttle scopes don't match the scopes actually present in the code.

## 9. Security Checklist

An app — or a change to one — isn't complete until each of these has been explicitly checked, not assumed:

**Application layer**
- No unauthenticated access to write endpoints unless explicitly intended.
- Object-level permission checks on top of class-level ones, to prevent one user reaching another user's object by ID (IDOR) — with a test per §7.4.
- Serializers used for writes list fields explicitly — never a blanket `fields = "__all__"` on anything user-writable.
- Sensitive fields (tokens, internal IDs, password hashes) are never exposed in a serializer's read output.
- No raw SQL without parameterization; no string-built queries. (`ruff`'s `S` rules catch most of this automatically now — see §3.1.)
- File uploads (if any) validate type and size server-side, not just client-side.
- No secrets or keys hardcoded — everything sensitive comes through `decouple.config(...)`, documented in the README `.env` block.
- Rate limiting (§4) and admin-vs-user permission separation (§5) are both in place, not deferred to "later."

**Supply chain**
- `pip-audit` (backend) and `npm audit --audit-level=high` (frontend) pass — both are CI jobs, see §10.
- No new dependency added without a look at what it pulls in transitively; `uv tree` shows the answer.
- Dependency ranges follow §1.1 — CI's `resolution-matrix` job proves the low end actually works.

The frontend-specific checklist lives in §12.

## 10. Continuous Integration

Every checklist in this document is worthless if a human has to remember to run it. CI is what turns them into gates. The design goal is that **an app repo's own workflow file is ~10 lines** — all real logic lives in one org-level reusable workflow, so improving CI once improves it for every app.

### 10.1 The org-level reusable workflow

Lives in a dedicated repo: `yourorg/.github`, at `.github/workflows/app-package-ci.yml`.

```yaml
name: app-package-ci

on:
  workflow_call:
    inputs:
      package-name:        # importable module name, e.g. notifications_app
        required: true
        type: string
      python-version:
        type: string
        default: "3.14"
      node-version:
        type: string
        default: "22"
      has-frontend:
        type: boolean
        default: true
      coverage-threshold:
        type: number
        default: 85
    secrets:
      ORG_READ_TOKEN:
        required: false   # only needed if this app depends on a private shared toolkit

jobs:
  # ---------------------------------------------------------------- backend
  backend-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      - run: uv run ruff check --output-format=github .
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run mypy src
        working-directory: backend

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
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
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      - name: Missing migrations check
        run: uv run python -m django makemigrations --check --dry-run
        working-directory: backend
        env:
          DJANGO_SETTINGS_MODULE: tests.backend.settings
      - name: pytest
        run: uv run pytest -n auto --cov-fail-under=${{ inputs.coverage-threshold }}
        working-directory: backend

  # Proves the DECLARED ranges work, not just the locked versions — see §3.4
  resolution-matrix:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        resolution: [lowest-direct, highest]
    services:
      postgres:
        image: postgres:17-alpine
        env: { POSTGRES_PASSWORD: postgres, POSTGRES_DB: test_db }
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
    env:
      POSTGRES_HOST: localhost
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --resolution ${{ matrix.resolution }} --upgrade
        working-directory: backend
      - run: uv run pytest -n auto --no-cov
        working-directory: backend

  # Proves the built wheel actually contains templates/locale/static — §2
  wheel-smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
        working-directory: backend
      - name: Install the wheel into a clean env and import it
        working-directory: backend
        run: |
          uv venv /tmp/smoke
          uv pip install --python /tmp/smoke/bin/python dist/*.whl
          /tmp/smoke/bin/python -c "import ${{ inputs.package-name }}; print('import ok')"
      - name: Assert package data shipped
        working-directory: backend
        run: |
          python - <<'PY'
          import glob, sys, zipfile
          whl = glob.glob("dist/*.whl")[0]
          names = zipfile.ZipFile(whl).namelist()
          missing = [
              kind for kind, pat in (("templates", "/templates/"), ("locale", ".mo"))
              if not any(pat in n for n in names)
          ]
          if missing:
              sys.exit(f"wheel is missing package data: {missing} — check MANIFEST.in")
          print("package data ok")
          PY

  security-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uvx pip-audit --strict -r <(uv export --no-dev --format requirements-txt)
        shell: bash
        working-directory: backend

  # ---------------------------------------------------------------- frontend
  frontend:
    if: ${{ inputs.has-frontend }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run test -- --run --coverage
        working-directory: frontend
      - run: npm audit --audit-level=high
        working-directory: frontend
      - run: npm run build
        working-directory: frontend

  # ---------------------------------------------------------------- contract gates
  version-lockstep:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: pyproject, package.json and CHANGELOG must agree
        run: |
          PY=$(grep -m1 '^version' backend/pyproject.toml | sed 's/.*"\(.*\)"/\1/')
          JS=$(node -p "require('./frontend/package.json').version")
          CL=$(grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md)
          echo "pyproject=$PY package.json=$JS changelog=$CL"
          test "$PY" = "$JS" && test "$PY" = "$CL" \
            || { echo "::error::version mismatch — see APP-DESIGN.md §11"; exit 1; }
      - name: On a tag, the tag must match too
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          PY=$(grep -m1 '^version' backend/pyproject.toml | sed 's/.*"\(.*\)"/\1/')
          test "v$PY" = "${GITHUB_REF_NAME}" \
            || { echo "::error::tag ${GITHUB_REF_NAME} != version v$PY"; exit 1; }

  no-inter-app-imports:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Backstop grep for sibling app imports
        run: |
          if grep -rnE '^\s*(from|import)\s+[a-z_]+_app' backend/src \
               --include='*.py' \
               | grep -v '${{ inputs.package-name }}'; then
            echo "::error::app package imports another app package — see APP-DESIGN.md §6"
            exit 1
          fi
      - name: Factories must not be imported by production code
        run: |
          if grep -rn 'factories' backend/src --include='*.py' \
               | grep -v 'factories.py'; then
            echo "::error::factories.py is a test-only surface — see APP-DESIGN.md §7.3"
            exit 1
          fi

  readme-contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Every throttle_scope in code appears in README
        run: |
          fail=0
          for scope in $(grep -rhoE 'throttle_scope\s*=\s*"[^"]+"' backend/src \
                          | sed 's/.*"\(.*\)"/\1/' | sort -u); do
            grep -q "$scope" README.md || { echo "::error::scope $scope missing from README"; fail=1; }
          done
          exit $fail
```

### 10.2 What an app repo actually commits

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:

jobs:
  ci:
    uses: yourorg/.github/.github/workflows/app-package-ci.yml@main
    with:
      package-name: notifications_app
      coverage-threshold: 85
    secrets: inherit
```

### 10.3 Branch protection & automation

- Require `backend-quality`, `backend-tests`, `frontend`, `version-lockstep`, and `no-inter-app-imports` to pass before merge to `main`. The rest (`resolution-matrix`, `security-audit`) can be advisory at first and promoted once they're stable.
- **Renovate** (preferred over Dependabot here, because it handles the `git+...@vX.Y.Z` tag pattern and `uv.lock` better) opens PRs for: `uv.lock` updates within declared ranges, `package-lock.json`, the pinned Docker base image digests in `playground/`, and pre-commit hook `rev`s. Group patch updates into one weekly PR; keep majors separate so they get read.
- **Conventional Commits** (`feat:`, `fix:`, `feat!:`) make the semver decision in §11 mechanical instead of a judgement call, and let `git-cliff` generate the `CHANGELOG.md` section from history. Enforce with a `commitlint` job or a `commit-msg` pre-commit hook.

## 11. Release Workflow

### 11.1 Order of operations

1. **Green CI on `main`.** Not "tests passed locally" — the full workflow from §10, including `resolution-matrix` and `wheel-smoke-test`. These two are the ones that catch the failures a host would otherwise discover for you.
2. **Playground verification** (§11.2) — prove the two halves work together against a real host before tagging.
3. **Decide the bump** from the Conventional Commit history: any `!`/`BREAKING CHANGE` → major; any `feat:` → minor; otherwise patch. Remember from §6 that a changed signal payload, a changed `services.py` signature, or a renamed factory is a **major**, even if the diff looks tiny.
4. **Bump the version in three places together:** `backend/pyproject.toml`, `frontend/package.json`, and a new `CHANGELOG.md` section. CI's `version-lockstep` job fails the build if they disagree, so this cannot be forgotten silently.
5. **Update `README.md`'s config block** (§8) if settings, `.env` keys, throttle scopes, URLs, signal payloads, service signatures, factories, or exported hooks changed.
6. **Commit, tag `vX.Y.Z`** (one tag covers both halves), push the tag. The tag push re-runs CI with the tag-match assertion active.
7. **In a consuming project**, follow `INTEGRATION-GUIDE.md` §2's upgrade path.

### 11.2 The `playground/`

`playground/` is a minimal Django + Next.js host living in the app's own repo, with both halves linked by **path**, not by tag. Use `[tool.uv.sources]` for this rather than an editable install flag — it redirects where a dependency resolves from without changing the dependency declaration, so the same `pyproject.toml` line works for both dev and release:

```toml
# playground/backend/pyproject.toml
[project]
dependencies = ["notifications-app"]

[tool.uv.sources]
notifications-app = { path = "../../backend", editable = true }
```

```bash
cd playground/backend && uv sync         # picks up your working tree, live
cd playground/frontend && npm install    # package.json uses "file:../../frontend"
docker compose -f playground/docker-compose.yml up
```

This is what catches "the hook's shape drifted from the API's actual response" before a host project does — the single highest-value pre-release check, because it's the one thing no unit test on either half can prove.

### 11.3 `CHANGELOG.md` format

Keep a Changelog, so "did v1.5.0 change my throttle scopes?" is answerable at a glance:

```markdown
# Changelog

## [1.5.0] — 2026-08-14

### Added
- `useNotificationPreferences` hook and matching `/preferences/` endpoint.

### Changed
- `notifications_list` throttle default raised from 30/min to 60/min.
  **Host action:** update `DEFAULT_THROTTLE_RATES` if you copied the old value.

### Fixed
- N+1 query on the list endpoint when `channel` was prefetched.
```

Any entry that requires the host to change something says so explicitly, under a **Host action:** line. That line is the difference between a smooth upgrade and a mystery.

## 12. Frontend SDK Contract

The `frontend/` half of a package is a small SDK — typed hooks and a fetcher, nothing more. It follows the same decoupling discipline as the backend half, adapted to React:

- **One entrypoint.** Everything a host can use is exported from `frontend/src/index.ts`. Nothing under `hooks/`, `api/`, or `types.ts` is imported directly by a host — only through `index.ts`. This keeps the internal file layout free to change without it being a breaking change.
- **Peer dependencies, not bundled ones.** `react`, `@tanstack/react-query` (or `axios`, whichever the app actually uses) are declared as `peerDependencies`, never as regular `dependencies`. Bundling them would mean a host ends up with two copies of React or two separate `QueryClient` instances — a well-known source of hard-to-debug bugs. The host's own copy, already provided via the scaffold's `frontend/lib/query-client.ts` (see `BASE-DESIGN.md` §3), is what every hook plugs into.
- **No inter-app frontend dependencies.** Exactly like the backend half (§6), a package's `frontend/` must never depend on or import another reusable app's frontend package. If two apps' UIs need to be combined, that composition happens in the host's own `frontend/` code — see `INTEGRATION-GUIDE.md` §4.
- **Typed end to end, strictly.** `tsconfig.json` sets `"strict": true`; `types.ts` exports the request/response shapes the hooks use, so a host gets full type safety with no separate `@types` package and no `any`.

```json
// frontend/package.json (excerpt)
{
  "name": "notifications-app",
  "version": "1.4.2",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": { ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js" } },
  "files": ["dist"],
  "peerDependencies": {
    "react": ">=18",
    "@tanstack/react-query": ">=5"
  },
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest",
    "lint": "eslint src"
  }
}
```

The `exports` map matters: it's what stops a host from importing `notifications-app/dist/api/manager` and coupling itself to internals, which the "one entrypoint" rule exists to prevent. Declaring only `"."` makes the rule enforced by Node's resolver rather than by convention.

### Manager & hook conventions

Every app's frontend has two layers, mirroring the backend's `views.py` + `services.py` split:

- **The manager** (`api/manager.ts`) is a plain class with one static/instance method per backend endpoint. It's the *only* place a raw HTTP call happens — no `fetch`/`axios` call exists anywhere outside this file. It's typed against `types.ts`, and it's never exported from `index.ts` — a host only ever reaches it indirectly, through a hook.
- **Hooks** (`hooks/*.ts`) are thin `@tanstack/react-query` wrappers around manager methods — never anything more. A query hook wraps `useQuery` with a stable, namespaced `queryKey` (`["notifications", ...]`, per §1.3); a mutation hook wraps `useMutation` and invalidates the relevant query keys on success. Neither swallows loading/error state — every hook returns the standard react-query result object as-is, so the host UI decides how to render `isLoading`/`isError`, rather than the SDK imposing a spinner or toast opinion. If two hooks share logic (e.g. an error-shape normalizer), factor it into an internal, unexported helper.

```ts
// frontend/src/api/manager.ts
import { apiClient } from "./client";
import type { Notification, SendNotificationPayload } from "../types";

export class NotificationsManager {
  static list(): Promise<Notification[]> {
    return apiClient.get<Notification[]>("/");
  }

  static send(payload: SendNotificationPayload): Promise<Notification> {
    return apiClient.post<Notification>("/send/", payload);
  }
}
```

```ts
// frontend/src/hooks/useNotifications.ts
import { useQuery } from "@tanstack/react-query";
import { NotificationsManager } from "../api/manager";

export const notificationKeys = {
  all: ["notifications"] as const,
  list: () => [...notificationKeys.all, "list"] as const,
};

export function useNotifications() {
  return useQuery({
    queryKey: notificationKeys.list(),
    queryFn: NotificationsManager.list,
  });
}
```

```ts
// frontend/src/hooks/useSendNotification.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NotificationsManager } from "../api/manager";
import { notificationKeys } from "./useNotifications";
import type { SendNotificationPayload } from "../types";

export function useSendNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SendNotificationPayload) => NotificationsManager.send(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}
```

```ts
// frontend/src/index.ts — the only file a host ever imports from; note the
// manager is never exported here, only hooks, key factories, and types
export { useNotifications, notificationKeys } from "./hooks/useNotifications";
export { useSendNotification } from "./hooks/useSendNotification";
export type { Notification, SendNotificationPayload } from "./types";
```

Exporting the `notificationKeys` factory is deliberate: a host sometimes needs to invalidate this app's cache from its own code (after a cross-app action composed in `frontend/app/`, per `INTEGRATION-GUIDE.md` §4). Without the factory, the host hardcodes the key string and silently breaks when the SDK changes it.

### Frontend security checklist

Parallel to the backend checklist in §9 — a frontend half isn't done until each of these is checked, not assumed:

- No sensitive tokens (auth tokens, API keys) stored in `localStorage`/`sessionStorage` from within the package's own code — rely on the host's existing auth/cookie handling rather than the app inventing its own storage.
- Manager methods never build a URL by concatenating unescaped user input — values always go through the client's param/body encoding, never string-interpolated into a path.
- No `dangerouslySetInnerHTML` with unsanitized data, if the package ships any UI components beyond hooks.
- No hardcoded base URLs, API keys, or secrets anywhere in the package — the base URL always comes from the host's shared client configuration.
- A mutation hook for a destructive or sensitive action (`useDeletePaymentMethod`, `useCreatePayment`) never fires on mount or on a passive render — it only fires from an explicit user action, so a stray re-render can't trigger a real charge or deletion.
- Every manager method and hook is typed against `types.ts` — no `any` on a request/response shape, since a silently wrong type is exactly how a backend contract drifting out from under a hook turns into a runtime bug nobody notices until it's in production.
- `react` and `@tanstack/react-query` stay `peerDependencies`, never bundled.
- `npm audit --audit-level=high` passes (CI job, §10).
