# CLAUDE.md — base-scaffold (the template itself)

This repo is a one-time starter kit, not a running project: projects clone it, delete .git,
and own the result. There is no upstream pull, so a mistake here propagates into every future
project and has to be fixed N times. Bias hard toward correctness over speed.

## The spec
`docs/BASE-DESIGN.md` is authoritative for everything in this repo. Read the relevant section
before implementing — do not infer structure from convention or memory. `docs/APP-DESIGN.md`
and `docs/INTEGRATION-GUIDE.md` describe what will be installed into this scaffold later;
consult them whenever a decision here constrains them.

When this repo and the spec disagree, the spec wins — unless you believe the spec is wrong,
in which case **stop and say so** rather than silently implementing something better.

## Pinned versions & defaults

These are the concrete decisions behind this scaffold — cite this table instead of
re-deriving a version from `BASE-DESIGN.md` prose. Changing one is a real decision;
update it here and in every file it's baked into (`.python-version`, Docker base images,
`pyproject.toml`, `package.json`, CI workflow), not just one of them.

| Decision | Value |
|---|---|
| Python | 3.14 — `.python-version` and every Docker base image (`python:3.14-slim`) |
| Node | 22 LTS — `node:22-alpine` in Docker, `engines` in `package.json` |
| Postgres | 17 — dev, test, and prod. Never SQLite |
| Redis | 7 — `redis:7-alpine` in every compose file |
| Django | 6+ on ASGI (Uvicorn) |
| uv | 0.11 — `ghcr.io/astral-sh/uv:0.11` in both backend Dockerfiles. Must track the toolchain that writes `backend/uv.lock` (currently uv 0.11.19, lockfile `revision = 3`) — uv refuses a lockfile revision newer than it supports, so this pin is not cosmetic |
| Frontend package manager | npm — `package-lock.json` committed, `npm ci` in CI/Docker. Only move to pnpm as a deliberate, recorded decision |
| Coverage threshold | 80% (`--cov-fail-under=80`) |
| Sentry | Included by default, wired to `SENTRY_DSN`; empty by default so it's inert in dev/CI and active the moment a DSN is set |
| Placeholder project name | `myproject` — what `scripts/rename-project.sh` replaces in `.env.example`, `docker-compose*.yml`, `CLAUDE.md`, `pyproject.toml`, `package.json` |
| GitHub org | Stays the `{{ORG}}` placeholder in this repo (`CLAUDE.md.template`, install commands). A cloned project fills in its real org — install commands (`uv add git+https://github.com/<org>/...`) don't work otherwise |

## Non-negotiables for this repo
- `uv` only. No `requirements.txt`, no `pip install`, anywhere, ever.
- Postgres only. No SQLite, including in tests.
- Django 6+ on ASGI. No `gunicorn`, no `wsgi:application` in any run command.
- No authentication anywhere in this scaffold — auth is an installed app package.
- Nothing project-specific. No client names, no business logic, no domain models.
  Placeholders where a project must fill something in.
- Dev and prod are separate Dockerfiles and separate compose files. Never one shared.
- Prod containers run as a non-root user. Dev may run as root (bind-mount ownership).
- Every secret comes from .env via decouple.config, with no default for required values.

## Working agreement
- Implement one phase at a time. Do not create files outside the current phase's scope.
- Before writing a file that the spec shows, re-read that part of the spec.
- After each phase, run the phase's verification command and paste the real output.
  Never report success you haven't observed.
- If something in the spec is ambiguous or looks wrong, ask. Do not guess and proceed.
- Prefer boring, explicit, standard code. Cleverness here is a liability: this code gets
  read and modified by people (and agents) who have never seen it before.

## Git protocol
- Never stage or commit unless I explicitly ask. I review every diff before it lands.
- Never `git push`, `git reset --hard`, `git checkout <branch>`, force-push, or amend an
  existing commit. Ever. Ask instead.
- When a phase or task is done, don't commit. Instead:
  1. Summarise what changed and the verification output that passed.
  2. Propose a commit message in the exact format below, in a fenced code block so I can
     copy it verbatim.
  Then stop and wait. I'll review, then ask you to commit.
- If you think something needs reverting, say so and let me do it.

### Commit message format

```
semantic(<scope>): <short_commit_message>

Dashed description of changes

Add <what was added>
Remove <what was removed>
Update <what was changed>
```

Rules for it:
- `semantic` is one of: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`,
  `perf`, `style`. Use `!` after the scope for a breaking change: `feat(core)!:`.
- `<scope>` is the area touched, lowercase, one word where possible — `backend`, `frontend`,
  `core`, `config`, `docker`, `ci`, `deps`, `tooling`, `deploy`. Use the narrowest scope that
  covers the change; if a change genuinely spans everything, it's probably two commits.
- `<short_commit_message>` is imperative mood, lowercase, no trailing period, under 60 chars
  — "add uv project config", not "Added uv project config."
- Keep the literal line `Dashed description of changes` as the body's first line, then a
  blank line, then the bullets.
- One bullet per meaningful change, each starting with an imperative verb (`Add`, `Remove`,
  `Update`, `Move`, `Rename`, `Fix`, `Pin`, `Enable`, `Disable`). Capitalised, no trailing
  period. Group trivia rather than listing every file — bullets describe changes, not a
  file inventory.
- If a change requires action from me or from a host project (a new `.env` key, a manual
  migration, a config block to copy), add a final line: `Host action: <what to do>`.
- No co-author trailers, no "generated with" footers, no emoji.

Example:

```
chore(backend): add uv project config and tooling baseline

Dashed description of changes

Add backend/pyproject.toml with dependencies, dev/test dependency groups and uv default-groups
Add ruff, mypy, pytest and coverage configuration
Add commented banned-api table enforcing the core/-only app import rule
Add MANIFEST.in, .python-version and .dockerignore
Update .gitignore to cover .venv, .ruff_cache and .mypy_cache
```