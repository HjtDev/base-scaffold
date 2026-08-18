# Only the `test` target for now — Phase 3 is the first phase with tests, so it's pulled
# forward from BASE-DESIGN.md §10.2. The rest of the Makefile (up/down/logs/lint/...) arrives
# with the compose stack in Phase 8.
.PHONY: test

test:          ## Run the host test suite against an ephemeral Postgres + Redis
	docker compose -f docker-compose.test.yml up -d --wait
	cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow"
	docker compose -f docker-compose.test.yml down
