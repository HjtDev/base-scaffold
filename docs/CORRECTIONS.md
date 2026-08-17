# CORRECTIONS.md — places this repo deliberately deviates from the spec

`CLAUDE.md` says: "When this repo and the spec disagree, the spec wins — unless you believe the
spec is wrong, in which case stop and say so." This file is where "said so" gets recorded, so a
deviation is a documented, one-time decision instead of something re-litigated (or silently
reverted) every time an agent reads the spec fresh. Each entry names the spec section, what it
says, what this repo does instead, and why.

## 1. Pre-commit mypy hook is `repo: local`, not a pinned mirror

**Spec:** `docs/APP-DESIGN.md` §3.6 shows mypy as a pinned-`rev` mirror hook.

**This repo:** `.pre-commit-config.yaml` runs mypy (and ruff, ruff-format) as a `repo: local`
hook shelling out via `uv run`, per `docs/BASE-DESIGN.md` §5.1's own explicit instruction.

**Why:** A mirror hook's isolated venv only ships `[django-stubs, djangorestframework-stubs]` —
not enough for `strict = true` + `mypy_django_plugin` + a `django_settings_module`, which needs
the whole project importable. `repo: local` resolves from `uv.lock`, so pre-commit and CI can
never run a different mypy version than the one everyone else uses.

## 2. The `*.factories` banned-api entry is a grep hook, not a ruff rule

**Spec:** `docs/BASE-DESIGN.md` §5.2 asks for a `*.factories` entry alongside the `banned-api`
table.

**This repo:** enforced instead by the `no-factories-in-core` local hook in
`.pre-commit-config.yaml` (and the equivalent CI grep), documented inline in
`backend/pyproject.toml`'s `banned-api` comment block.

**Why:** `banned-api` violations all report as rule code `TID251`, and `per-file-ignores` disables
a rule *code* for a path. `core/**` must already ignore `TID251` (production `core/` legitimately
imports app packages — that's its purpose), so any factories entry in `banned-api` would be
silently disabled throughout `core/`, including the production code it's meant to catch. There is
no way to re-enable a rule for a subpath, so this rule can't be expressed in ruff at all here — it
has to be a grep.

## 3. Security settings block added to `config/settings.py`, not shown in §4.3's excerpt

**Spec:** `docs/BASE-DESIGN.md` §4.3's settings code block has no `SECURE_*`/cookie/HSTS settings.
§7's CI job runs `manage.py check --deploy --fail-level WARNING` with `DEBUG=False`, which fails
on `security.W004/W008/W012/W016` against an otherwise-unset settings module.

**This repo:** `config/settings.py` adds an explicit security block, all values env-driven via
`decouple.config(...)`, defaulting to `not DEBUG`:

- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` default to `_SECURE_DEFAULT = not DEBUG`.
- `SECURE_HSTS_SECONDS` defaults to **`0` in every environment**, including prod, and must be set
  explicitly (`backend/.env.prod.example` sets `31536000` with a comment). HSTS at a year is
  effectively irreversible for the domain and every subdomain — a wrong-but-easy inherited default
  here can take an unrelated subdomain offline for months, so it's a deliberate act, not a default.
- `SECURE_HSTS_INCLUDE_SUBDOMAINS` / `SECURE_HSTS_PRELOAD` derive from `SECURE_HSTS_SECONDS > 0`.
- `SECURE_PROXY_SSL_HEADER` is set only when `TRUST_PROXY_SSL_HEADER` (default `not DEBUG`) is
  true — trusting `X-Forwarded-Proto` unconditionally is a spoofing vector the moment the
  container is reachable without the proxy in front.
- `SESSION_COOKIE_HTTPONLY = True`; `CSRF_COOKIE_HTTPONLY = False` explicitly, commented, because
  the Next.js frontend must read the CSRF cookie in JS to send the header.

**Follow-up needed in the spec:** `docs/BASE-DESIGN.md` §4.3's excerpt should include this block,
and §7's `backend-tests` CI env needs `SECURE_HSTS_SECONDS: "31536000"` added or `check --deploy`
fails as currently written.

## 4. `jazzmin` precedes `django.contrib.admin` in `INSTALLED_APPS`

**Spec:** `docs/BASE-DESIGN.md` §4.3 lists `"django.contrib.admin"` before `"jazzmin"`.

**This repo:** `jazzmin` is listed first, with an inline comment explaining why.

**Why:** django-jazzmin overrides the admin's templates via Django's app-directories template
loader, which resolves to the *first* matching app in `INSTALLED_APPS`. Reversed, as the spec
shows it, the admin still renders — just permanently unthemed, silently, with nothing in the test
suite or CI to catch it. Someone alphabetising the list later is a realistic way for this to
regress even after being fixed once, which is why Phase 3 adds a wiring smoke test asserting
`INSTALLED_APPS.index("jazzmin") < INSTALLED_APPS.index("django.contrib.admin")`.

**Follow-up needed in the spec:** `docs/BASE-DESIGN.md` §4.3's `INSTALLED_APPS` excerpt should
swap the two lines and carry this comment across — there's no prose claim to fix, only the
ordering in that code block.

## 5. Request-ID contextvar, middleware, and filter all live in `config/logging.py`

**Spec:** `docs/BASE-DESIGN.md` §3 requires both logging configs to carry a request ID for
correlation, but names no package for it and doesn't say where the plumbing lives. §2's `config/`
tree doesn't list a `middleware.py`.

**This repo:** the `ContextVar`, an async-capable `RequestIDMiddleware`, and a
`logging.Filter` all live in `config/logging.py`, alongside `build_logging_config()`. No new
dependency — `contextvars` and `logging.Filter` are stdlib.

**Why:** all three exist solely to serve `build_logging_config`, so co-locating them keeps the
`config/` tree exactly as specified rather than adding a file the spec doesn't list.

**Follow-up needed in the spec:** `docs/BASE-DESIGN.md` §3's logging bullet should name
`config/logging.py` as the home for the contextvar, middleware, and filter, and state explicitly
that it adds no dependency.

## 6. WebSocket composition point — a gap, not a bug

**Spec:** `docs/BASE-DESIGN.md` §3 (pre-Phase-2 revision) said Django 6 runs on ASGI via
Uvicorn and that `daphne` was "a fine substitute if an installed app package ends up needing
native WebSocket routing through `asgi.py`" — but never said *how* that routing gets composed,
who owns `config/asgi.py`'s `ProtocolTypeRouter`, or that `get_asgi_application()` must run
before any consumer import. This wasn't a wrong statement to correct; it was a gap the design
never closed, and it needed closing before any app package could ship a WebSocket consumer.

**This repo:** added a "WebSockets" subsection to `docs/BASE-DESIGN.md` §3 stating Channels is
deliberately excluded from the base scaffold for the same reason auth is (most projects don't
need it; opting in is cheap when one does), that `uvicorn[standard]` already speaks WebSocket
so nothing about the ASGI server needs to change, and showing the exact `ProtocolTypeRouter`
composition a project adds in `config/asgi.py` when it does need one — including the ordering
requirement (`get_asgi_application()` before any consumer import, or consumer code that
touches models raises `AppRegistryNotReady`) and the nginx `Upgrade`/`Connection` header
handling that's a deploy-side change too, not only application code.

**Also corrected in passing:** §3's Uvicorn bullet implied Daphne might be *needed* for
WebSocket support. It isn't — Daphne is Channels' reference ASGI server, not a requirement;
`uvicorn[standard]` handles it.

## 7. Realtime as an app package's fourth public surface — a gap, not a bug

**Spec:** `docs/APP-DESIGN.md` §6 defines an app package's public surfaces as `signals.py`,
`services.py`, and (test-only) `factories.py`. It never addressed what a package exposes if it
needs to push data over a WebSocket, or how that composes with the host without violating the
same "no app imports another app" rule §6 exists to enforce. Same category as #6: a gap left
by realtime being out of scope until a project opts in, not a mistake to walk back.

**This repo:** added a "Realtime (optional fourth surface)" subsection to `docs/APP-DESIGN.md`
§6 defining `routing.py` (`websocket_urlpatterns`) + `consumers.py` as that fourth surface,
mirroring `urls.py`/`urls_admin.py`; stating the host mounts it explicitly in `config/asgi.py`
with nothing auto-discovered, same as every other wiring point in this ecosystem; requiring
`channels` be declared as a wide-range *optional* dependency (an extra) so the package still
installs into a host that isn't running Channels; restating that §6's "never import another
app package" rule applies to consumers unchanged, with `core/signals.py` calling
`channel_layer.group_send(...)` as the mediator; and — the one substantive design decision in
this entry — establishing that WebSocket auth (a token in the query string or subprotocol,
since a browser can't set an `Authorization` header on a socket handshake) belongs in the auth
app package as a `JWTAuthMiddlewareStack`-shaped export, not reimplemented by every app that
ships a consumer.
