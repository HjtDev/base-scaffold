# syntax=docker/dockerfile:1.7
# Dev backend image — BASE-DESIGN.md §8.1. Single-stage on purpose: with the source
# bind-mounted, a builder stage buys nothing and costs rebuild time. Runs as root
# deliberately — bind-mounted files owned by your host user are otherwise unwritable by a
# container user, which breaks `makemigrations` in the most annoying possible way. That
# trade is acceptable in dev and unacceptable in prod, which is why these are two files.
FROM python:3.14-slim
# Same version note as Dockerfile.prod: pinned to match backend/uv.lock's revision.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# UV_PROJECT_ENVIRONMENT puts the venv OUTSIDE the bind mount. docker-compose.yml mounts
# ./backend at /app, so a venv at the default /app/.venv would be shadowed by whatever's
# on the host (nothing, on a fresh clone — .venv is gitignored) the moment the mount
# lands. §8.1's ".venv gotcha" paragraph names this exact fix; PATH must follow it.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev pkg-config git postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

# No --no-default-groups / --no-dev here: dev wants both the dev and test groups
# ([tool.uv] default-groups in backend/pyproject.toml already selects them).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Kept even though compose bind-mounts over it, so `docker compose run --no-deps backend`
# still works without the mount. These four dirs are gitignored, so a fresh clone's bind
# mount hides them again on top — harmless: config/logging.py has no file handler, and
# STATIC_ROOT/MEDIA_ROOT are only ever touched by collectstatic and file uploads, neither
# of which happens routinely in dev.
COPY . /app
RUN mkdir -p /app/logs /app/static /app/staticfiles /app/media

EXPOSE 8000
# exec puts runserver at PID 1 so it receives SIGTERM directly — without it, `docker
# compose down` waits out the full stop timeout on every service using this image.
CMD ["sh", "-c", "python manage.py migrate && exec python manage.py runserver 0.0.0.0:8000"]
