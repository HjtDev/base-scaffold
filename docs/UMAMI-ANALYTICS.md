# UMAMI-ANALYTICS.md — self-hosted Umami analytics reference

Optional, off-by-default self-hosted [Umami](https://umami.is) analytics for a project cloned
from this scaffold. This is the implementation reference; `README.md`'s "Analytics (optional)"
section is the short version for a first-time setup. Both describe the same feature — this
file exists so the reasoning behind each decision has one findable home instead of being
scattered across compose comments.

Supersedes two earlier working documents (an old reference implementation from a prior
project, and the brief written from it) — both are folded in here and no longer exist
separately, since several of the old guide's specifics were wrong for this scaffold (see
"Deviations from the original reference implementation" below).

## Why off by default

A project that doesn't pay for analytics should carry no extra containers and no third-party
script tag. Everything here is gated behind a compose profile named `analytics` and a single
frontend env var — nothing is active unless a project deliberately turns it on.

## What's included

Two services, `umami` and `umami-db`, defined in both `docker-compose.yml` and
`docker-compose.prod.yml` behind `profiles: ["analytics"]`:

- **`umami-db`** — `postgres:17-alpine`, a database **separate** from the app's own `db`
  service. Umami owns and migrates its own schema on boot; sharing an instance with the app
  would couple the app's migration state to a third-party container's.
- **`umami`** — `ghcr.io/umami-software/umami:3.3.1`, talking to `umami-db`.

Neither starts with a plain `docker compose up` / `make up`. Bring them up with:

```bash
docker compose --profile analytics up --build   # or: make analytics
```

In prod, the profile is activated by uncommenting `COMPOSE_PROFILES=analytics` in the root
`.env.prod` — `deploy-prod.sh` already passes that file with `--env-file` on every compose
invocation, so no `--profile` flag needs to be threaded through the deploy script itself.

## Environment variables

| Key | Where | Purpose |
|---|---|---|
| `UMAMI_PORT` | root `.env` / `.env.prod` | Host port `umami` is published on (default `3001`). Bound to `127.0.0.1` in prod. |
| `UMAMI_DB_PASSWORD` | root `.env` / `.env.prod` | `umami-db`'s Postgres password. Dev has a working default; prod ships empty and required. |
| `UMAMI_APP_SECRET` | root `.env` / `.env.prod` | Session/crypto secret for the Umami app itself. |
| `UMAMI_TWO_FACTOR_ENCRYPTION_KEY` | root `.env` / `.env.prod` | 64 hex chars. Required before any Umami user can enable 2FA (new in Umami v3.3). See "Security" below for why this is shipped even though nothing forces 2FA on. |
| `NEXT_PUBLIC_UMAMI_SCRIPT_URL` | root `.env` / `.env.prod` (frontend build arg in prod) | The public URL of Umami's tracker script, e.g. `https://analytics.example.com/script.js`. |
| `NEXT_PUBLIC_UMAMI_WEBSITE_ID` | root `.env` / `.env.prod` (frontend build arg in prod) | The site's Website ID from the Umami dashboard. **Empty means analytics stays off** — `frontend/app/layout.tsx` renders no `<Script>` tag at all when this is unset. |

Generate the two secrets the same way `SECRET_KEY`/`FERNET_KEY` are generated elsewhere in
this repo:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # UMAMI_DB_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # UMAMI_APP_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"       # UMAMI_TWO_FACTOR_ENCRYPTION_KEY
```

### Why prod's compose file uses `:-` instead of `:?` for these secrets

Compose interpolates every service's variables at parse time regardless of which profiles are
active — so a `:?` guard on `UMAMI_DB_PASSWORD` etc. would break `docker compose build` for
every project that never enables analytics, even though the `umami`/`umami-db` services
themselves would never be built or started. `docker-compose.prod.yml` uses an empty (`:-`)
default for exactly these three keys instead. The real enforcement lives in
`deploy/deploy-prod.sh` step 7: if `COMPOSE_PROFILES` in the server's `.env.prod` contains
`analytics`, the deploy fails loudly, before rsync-ing or touching the database, if any of the
three are still empty.

## The one env-toggle exception in this scaffold

`NEXT_PUBLIC_UMAMI_SCRIPT_URL` and `NEXT_PUBLIC_UMAMI_WEBSITE_ID` are inlined into the
frontend's bundle at **build** time (`frontend/Dockerfile.prod`'s `ARG`/`ENV` promotion,
mirroring `NEXT_PUBLIC_API_URL`). Every other env change in this project takes effect on a
container restart; these two don't. Enabling (or changing) analytics on an already-deployed
project requires rebuilding the frontend image:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build frontend
```

A plain `up -d` or restart does not pick up the new value.

## First-time setup

1. `make analytics` (dev) or a deploy with the profile enabled (prod).
2. Open the dashboard (`http://localhost:3001` in dev, `https://analytics.<domain>` in prod)
   and log in with the default `admin` / `umami` credentials.
3. **Change the password immediately** — see "Security" below; this is not optional.
4. Settings → Websites → Add website, then copy the generated Website ID.
5. Paste it into `NEXT_PUBLIC_UMAMI_WEBSITE_ID` (and set `NEXT_PUBLIC_UMAMI_SCRIPT_URL` to the
   public script URL for prod). In dev, restart the frontend container. In prod, rebuild it
   (see above).

## Security

Umami ships with a hardcoded `admin` / `umami` login. This **cannot be overridden by
environment variables** — [umami-software/umami#4083](https://github.com/umami-software/umami/issues/4083)
requested exactly that and was closed `not_planned` upstream, so the manual first-login
password change is a genuine, unavoidable manual step, not an oversight in this scaffold.

In a real client deployment, this dashboard sits at a public subdomain. Change the password
**before** the `analytics.<domain>` DNS record is made public — between those two moments,
anyone who finds the host owns the dashboard. `deploy-prod.sh` prints a reminder to do this
after any deploy where the analytics profile is active.

`UMAMI_TWO_FACTOR_ENCRYPTION_KEY` is shipped as a required prod key specifically so 2FA is
*available* to turn on once logged in — the strongest mitigation upstream offers, given that
the password itself can't be pre-set.

## Deployment (nginx)

This scaffold does not generate or manage nginx config — that's host-level setup the operator
owns (`docs/BASE-DESIGN.md` §9). If analytics is enabled, add a server block for the subdomain
you want the dashboard at, proxying to `127.0.0.1:${UMAMI_PORT:-3001}` (the port
`docker-compose.prod.yml` binds `umami` to on the host):

```nginx
server {
    listen 443 ssl;
    server_name analytics.example.com;

    # ... your TLS cert directives ...

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`umami` is bound to `127.0.0.1` in prod specifically so this proxy is the only way to reach
it — same reasoning as the backend and frontend ports (`docs/BASE-DESIGN.md` §9 step 8).

## Privacy

Umami is cookieless and privacy-friendly, but it still processes visitor data. Whether to
enable it on a given client project is that client's decision, with potential GDPR
implications — which is the other reason this defaults to off rather than being wired in
unconditionally.

## Deviations from the original reference implementation

The prior project's guide this was adapted from was written against Umami v2 and predates
several decisions this scaffold has since made. Deviations applied deliberately, verified
against upstream at the time of writing (Umami v3.3.1, August 2026):

- **`ghcr.io/umami-software/umami`, not Docker Hub's `umamisoftware/umami`.** The old guide
  said to use Docker Hub specifically; upstream's own `docker-compose.yml` now uses ghcr.io.
- **A pinned release tag (`3.3.1`), not `postgresql-latest`.** Umami v3 dropped MySQL support
  entirely, so the `postgresql-` tag prefix is a v2 artifact with no pinned version variants —
  the only option under that prefix is the moving `postgresql-latest` tag, which would defeat
  `renovate.json`'s `pinDigests`.
- **`postgres:17-alpine`, not `15`** — matches the app's own Postgres major; no reason to run
  two different major versions side by side.
- **`UMAMI_TWO_FACTOR_ENCRYPTION_KEY` added** — new in Umami v3.3, absent from the old guide's
  three-env-var list. See "Security" above.
- **No shared `app_network`.** This scaffold's compose files declare no explicit networks at
  all; every service uses the implicit compose default network, matching every other service
  here rather than introducing an exception for Umami.
- **Service names `umami`/`umami-db`** (hyphenated), not `umami`/`umami_db`, matching this
  repo's `celery-beat` naming convention.
