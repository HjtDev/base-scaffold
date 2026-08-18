# CORRECTIONS.md — history of where this repo and the spec diverged

`CLAUDE.md` says: "When this repo and the spec disagree, the spec wins — unless you believe the
spec is wrong, in which case stop and say so." This file is where "said so" got recorded during
Phases 1–3. Each finding has since been folded directly into `docs/BASE-DESIGN.md`,
`docs/APP-DESIGN.md`, or `docs/INTEGRATION-GUIDE.md` — those three are the single source of
truth from Phase 4 onward, not this file.

What's kept here is the **history**: a one-line pointer to where each correction landed and
what the original error was. Several of these are traps that will recur when the app-package
template gets built (the `banned-api`/factories subpath problem in particular), so the record
stays even though the docs no longer need it to be correct.

## Applied (Phases 1–3)

1. **Pre-commit mypy hook is `repo: local`, not a pinned mirror** — `docs/APP-DESIGN.md` §3.6, `docs/BASE-DESIGN.md` §5.1. Original spec text showed mypy as a pinned-`rev` mirror hook; a mirror's isolated venv can't satisfy `strict = true` + `mypy_django_plugin` + a `django_settings_module`, which needs the whole project importable.
2. **The `*.factories` rule is a grep hook, not a `banned-api` ruff entry** — `docs/BASE-DESIGN.md` §5.2. Spec asked for a `*.factories` entry in the `banned-api` table; `per-file-ignores` disables a rule *code* per path, and `core/**` must already ignore `TID251`, so a factories entry would be silently disabled exactly where it needs to catch violations — not expressible in ruff, enforced by grep instead.
3. **Security settings block (`SECURE_*`/cookie/HSTS)** — `docs/BASE-DESIGN.md` §4.3 (settings excerpt) and §7 (CI env). §4.3's shown code block omitted this block entirely, and without it `manage.py check --deploy --fail-level WARNING` (§7's CI job) fails against an otherwise-unset settings module.
4. **`jazzmin` precedes `django.contrib.admin` in `INSTALLED_APPS`** — `docs/BASE-DESIGN.md` §4.3. Spec's excerpt listed `django.contrib.admin` first; jazzmin overrides admin templates via the *first* matching app in `INSTALLED_APPS`, so the original ordering silently unthemes the admin with nothing to catch it.
5. **Request-ID `ContextVar`/middleware/filter live in `config/logging.py`** — `docs/BASE-DESIGN.md` §3. Spec required request-ID correlation but named no file for the plumbing and didn't list a `middleware.py` in §2's tree; co-located in `config/logging.py` instead, alongside `build_logging_config()`, since all three exist only to serve it.
6. **WebSocket composition point** — `docs/BASE-DESIGN.md` §3, "WebSockets" subsection. Not a wrong statement to correct, a gap: the spec never said how `config/asgi.py`'s `ProtocolTypeRouter` composition works, who owns it, or the `get_asgi_application()`-before-any-consumer-import ordering requirement.
7. **Realtime as an app package's fourth public surface** — `docs/APP-DESIGN.md` §6, "Realtime (optional fourth surface)" subsection. Same category as #6: the two-surface rule (`signals.py`/`services.py`) never addressed what a package exposes for a WebSocket consumer.
8. **The ephemeral test stack (`docker-compose.test.yml`) and a minimal `Makefile` pulled forward to Phase 3** — landed in the repo (`Makefile`, `docker-compose.test.yml`), not in one of the three design docs; their *content* (`docs/BASE-DESIGN.md` §5.3, §10.2) was already correct. `docs/CLAUDE-CODE-GUIDE-BASE.md`'s phase breakdown put these in Phases 5/8, leaving no phase before 8 with a tracked way to run the tests Phase 3 writes. **Not folded into the guide — it wasn't one of the three docs named for this pass; flagged as a decision, not silently applied.**
9. **`config/tests/` scoped into Phase 3, not left for later** — same shape as #8: a phase-sequencing fact, not a content error in `docs/BASE-DESIGN.md` §5.4 or `docs/INTEGRATION-GUIDE.md` §4 (both already correctly describe *what* to test). `backend/pyproject.toml`'s `--cov=config --cov-fail-under=80` makes this load-bearing regardless of which phase the guide assigns it to. **Same flag as #8.**
10. **The `tools/mixins.py` error envelope, previously unspecified** — `docs/BASE-DESIGN.md` §3 (envelope shape + `code` list) and `docs/APP-DESIGN.md` §4 (cross-reference). Spec described `tools/mixins.py` in one line ("shared DRF mixins/error formats") with no concrete shape for `APP-DESIGN.md` §4's "same shape" to point at.
11. **`docker-compose.test.yml`/`Makefile` `test` target gaps** — `docs/BASE-DESIGN.md` §5.3 and §10.2 (both code blocks). `test-redis` had no healthcheck, so `up -d --wait` didn't actually wait for it; the `test` target set only `POSTGRES_HOST`/`POSTGRES_PORT`, leaving the suite on `backend/.env`'s dev credentials and `redis://redis:6379/0` — neither reachable from the test containers.
12. **Bug, not a spec deviation: `RequestIDMiddleware` broke every real request** — `docs/BASE-DESIGN.md` §3 (logging bullet). A Phase 2 implementation bug, not a place the spec was wrong: the middleware never called `markcoroutinefunction(self)`, so `SecurityMiddleware` (wrapping it) couldn't detect it as async and called it without awaiting — confirmed to 500 every request through the real ASGI app, not just the test client. Found and fixed in Phase 3; regression-tested in `backend/config/tests/test_asgi_integration.py`.

## Open

*(nothing currently open)*
