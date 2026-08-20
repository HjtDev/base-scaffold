# base-scaffold

Django 6 (ASGI) + Next.js App Router monorepo starter. Clone it, name it, and it's yours —
`docs/BASE-DESIGN.md` §10.

```bash
# 1. Clone the scaffold — frontend/ and backend/ come together, already wired
git clone https://github.com/yourorg/base-scaffold.git my-client-project
cd my-client-project

# 2. Detach from the scaffold's history — from here on, this is just your code
rm -rf .git && git init

# 3. Name the project (drives container names, DB name, and CLAUDE.md's header)
./scripts/rename-project.sh my-client-project     # see docs/BASE-DESIGN.md §11

# 4. Environment
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
python3 -c "import secrets; print(secrets.token_urlsafe(64))"                              # SECRET_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # FERNET_KEY
# stdlib only — cryptography isn't installed until step 5, and its own Fernet.generate_key()
# output is byte-for-byte the same shape as this (32 random bytes, urlsafe-base64), so either
# is a valid key; this form just works before `uv sync` has run.
# paste both into backend/.env, then fill in DB creds and PROJECT_NAME

# 5. Python + Node dependencies
cd backend && uv sync --locked && cd ..    # --locked proves pyproject.toml and uv.lock agree
cd frontend && npm ci && cd ..

# 6. Hooks
uv run --directory backend pre-commit install

# 7. Bring the stack up
docker compose up --build

# 8. First superuser
docker compose exec backend python manage.py createsuperuser

# 9. Sanity check
open http://localhost:8000/healthz/     # 200
open http://localhost:8000/api/schema/swagger-ui/
open http://localhost:3000

# 10. Commit
git add . && git commit -m "chore: initial commit from base-scaffold vX.Y.Z"
```

Steps 5–6 are `make install`; step 7 is `make up`; `make check` is the definition of done from
here on (`docs/BASE-DESIGN.md` §10.2) — the explicit steps above are what those targets
actually run, spelled out once for a first read.

At this point the project is fully independent. Installing a reusable app package (both
halves) follows the protocol in `docs/INTEGRATION-GUIDE.md` §2, and there's no further contact
with the base-scaffold repo unless you're deliberately backporting an improvement by hand.
