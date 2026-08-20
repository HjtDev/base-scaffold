# syntax=docker/dockerfile:1.7
# Dev frontend image. docs/BASE-DESIGN.md §8 gives no code block for this file — only
# §8.2's table ("Source: bind-mounted", "npm run dev") and the Phase 5 brief's one line.
# Single-stage for the same reason backend/Dockerfile is: with the source bind-mounted, a
# multi-stage builder buys nothing and costs rebuild time.
FROM node:24-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# npm ci, never npm install — package-lock.json is committed (CLAUDE.md pinned versions).
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# docker-compose.yml mounts ./frontend at /app and layers anonymous volumes over
# /app/node_modules and /app/.next, so the host's copies (built for a different OS/arch,
# or simply absent on a fresh clone) never shadow the image's — the same shadowing
# problem backend/Dockerfile solves with UV_PROJECT_ENVIRONMENT. This COPY is what makes
# `docker compose run --no-deps frontend` work without those mounts.
COPY . .

# Runs as root, same bind-mount-ownership reason as backend/Dockerfile — a container user
# can't write into a directory bind-mounted from the host user's tree.
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
