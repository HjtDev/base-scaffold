# A thin, memorable interface over the real commands — BASE-DESIGN.md §10.2. Built up
# phase by phase as its prerequisites land, rather than all at once at the end:
#   Phase 3 added `test` (docker-compose.test.yml existed; nothing else did).
#   Phase 5 adds the compose-stack targets below (docker-compose.yml now exists).
# Still missing: lint/fmt/typecheck (compose targets that don't all exist yet) and
# check/deploy (check composes those; deploy needs Phase 7's deploy-prod.sh). See
# docs/CORRECTIONS.md for why the phase split differs from §10.2's single listing.
.DEFAULT_GOAL := help
.PHONY: help up down logs shell migrate migrations superuser test

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
