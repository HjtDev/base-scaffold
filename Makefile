# A thin, memorable interface over the real commands — BASE-DESIGN.md §10.2. Built up phase
# by phase as its prerequisites landed (Phase 3: test: Phase 5: compose-stack targets; Phase 8:
# everything below).
#
# `check` is defined as PARITY WITH .github/workflows/ci.yml: every job/step in CI maps to a
# target below, or is named as a deliberate exclusion. Any new CI step must be mirrored here or
# documented as excluded — that's the rule, not just this phase's intent (docs/BASE-DESIGN.md
# §10.2).
#
#   ci.yml job         step                                   make target
#   -----------         ----                                   -----------
#   backend-quality      uv sync --locked                       install
#                        ruff check .                            lint
#                        ruff format --check .                   lint
#                        mypy .                                   typecheck
#   backend-tests        uv sync --locked                       install
#                        makemigrations --check --dry-run        django-checks
#                        check --deploy --fail-level WARNING     django-checks
#                        pytest -n auto                           test
#   frontend             npm ci                                  install
#                        tsc --noEmit                             typecheck
#                        npm run lint                             lint
#                        npm run format:check                     lint
#                        npm run test -- --run                    test
#                        npm run build                             build
#   docker-build         prod image build + boot smoke test       EXCLUDED — a minutes-long
#                                                                  BuildKit run; `make up` and
#                                                                  `make deploy` already
#                                                                  exercise the same Dockerfiles
#   security-audit       pip-audit / npm audit                    EXCLUDED — a network CVE
#                                                                  lookup, advisory only in CI
#                                                                  (continue-on-error: true,
#                                                                  never a required check)
#
# `uv sync --locked` / `npm ci` are deliberately NOT part of `check` — re-installing on every
# check is slow and, for npm, destructive to node_modules. `make install` is the lock-drift
# gate: run it after touching pyproject.toml/uv.lock or package.json/package-lock.json.
.DEFAULT_GOAL := help
.PHONY: help install up down stop ps logs shell migrate migrations superuser backup restore \
        analytics lint fmt typecheck django-checks test test-fast build check deploy

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:       ## uv sync --locked + npm ci + install pre-commit hooks
	cd backend && uv sync --locked
	cd frontend && npm ci
	uv run --directory backend pre-commit install
	test -f backend/.env || echo "NOTE: backend/.env doesn't exist yet — see README.md step 4."

up:            ## Start the dev stack
	docker compose up --build
down:          ## Stop AND remove the dev stack's containers/network (use `stop` to keep them)
	docker compose down
stop:          ## Stop the dev stack in place — containers/volumes survive, `make up` resumes them
	docker compose stop
ps:            ## Show dev stack container status, including the health column
	docker compose ps
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
backup:        ## pg_dump the dev database to backups/<PROJECT_NAME>-<timestamp>.sql.gz
	mkdir -p backups
	name=$$(grep -m1 '^PROJECT_NAME=' .env 2>/dev/null | cut -d= -f2); \
	f="backups/$${name:-myproject}-$$(date +%Y%m%d-%H%M%S).sql.gz"; \
	docker compose exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' | gzip -9 > "$$f"; \
	echo "Wrote $$f"
restore:       ## Restore a backup into the dev database: make restore FILE=backups/<name>.sql.gz — drops and recreates the DB, confirms first
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/<name>.sql.gz" >&2; \
		exit 1; \
	fi; \
	if [ ! -f "$(FILE)" ]; then \
		echo "ERROR: $(FILE) not found." >&2; \
		exit 1; \
	fi; \
	if [ -f .env.prod ] || [ -f backend/.env.prod ]; then \
		echo "ERROR: .env.prod or backend/.env.prod exists in this repo checkout." >&2; \
		echo "Those files live ONLY on the production server (BASE-DESIGN.md §4.4/§9) —" >&2; \
		echo "this looks like a server checkout, not a local dev clone. Refusing to touch" >&2; \
		echo "it from here. See docs/BASE-DESIGN.md §9 'Restoring a backup' for the" >&2; \
		echo "server-side procedure." >&2; \
		exit 1; \
	fi; \
	cid=$$(docker compose ps -q db); \
	if [ -z "$$cid" ]; then \
		echo "ERROR: the dev 'db' service isn't running (docker compose ps -q db returned nothing)." >&2; \
		echo "Run 'make up' first." >&2; \
		exit 1; \
	fi; \
	dbname=$$(docker compose exec -T db sh -c 'echo $$POSTGRES_DB' < /dev/null); \
	dbuser=$$(docker compose exec -T db sh -c 'echo $$POSTGRES_USER' < /dev/null); \
	cname=$$(docker compose ps --format '{{.Name}}' db); \
	echo "This will DROP and recreate database '$$dbname' in container '$$cname',"; \
	echo "then load $(FILE) into it. ALL current data in '$$dbname' will be lost."; \
	printf "Type the database name (%s) to confirm: " "$$dbname"; \
	read -r confirm; \
	if [ "$$confirm" != "$$dbname" ]; then \
		echo "Confirmation did not match — aborting. Nothing was touched." >&2; \
		exit 1; \
	fi; \
	case "$(FILE)" in \
		*.gz) reader="gzip -dc '$(FILE)'" ;; \
		*) reader="cat '$(FILE)'" ;; \
	esac; \
	echo "Dropping and recreating '$$dbname'..."; \
	docker compose exec -T db dropdb --if-exists --force -U "$$dbuser" "$$dbname" < /dev/null; \
	docker compose exec -T db createdb -U "$$dbuser" -O "$$dbuser" "$$dbname" < /dev/null; \
	echo "Restoring $(FILE)..."; \
	eval "$$reader" | docker compose exec -T db psql -v ON_ERROR_STOP=1 --single-transaction -U "$$dbuser" -d "$$dbname"; \
	echo "Restore complete."
analytics:     ## Start the dev stack + Umami (compose profile: analytics)
	docker compose --profile analytics up --build

lint:          ## Ruff + ESLint + format checks (ruff format --check, prettier --check) — the CI gate
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check
fmt:           ## Fix everything lint checks for — the companion fixer, not run by `check`
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
typecheck:     ## mypy + tsc
	cd backend && uv run mypy .
	cd frontend && npx tsc --noEmit
django-checks: ## makemigrations --check + check --deploy, under a prod-shaped env — no setup needed
	cd backend && \
	SECRET_KEY=$$(python3 -c "import secrets; print(secrets.token_urlsafe(64))") \
	FERNET_KEY=$$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())") \
	DEBUG=False ALLOWED_HOSTS=localhost SECURE_HSTS_SECONDS=31536000 \
	EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
	sh -c 'uv run python manage.py makemigrations --check --dry-run && uv run python manage.py check --deploy --fail-level WARNING'
test:          ## Full suite (pytest + vitest) against an ephemeral Postgres + Redis — CI parity, what `check` runs
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  DEBUG=False SECURE_SSL_REDIRECT=False \
	  uv run pytest -n auto) && \
	(cd frontend && npm run test -- --run)
test-fast:     ## Backend only, skips slow tests — the inner-loop version of `test`, NOT what `check` runs
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow")
build:         ## Production frontend build — proves the Next.js build itself still succeeds
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
check: lint typecheck django-checks test build  ## Everything CI gates on, locally — the definition of done (see map above)
deploy:        ## Deploy to production (pass flags via ARGS, e.g. make deploy ARGS=--follow)
	./deploy/deploy-prod.sh $(ARGS)
