# AquaFarm Manager Ghana — Phase 1

Working FastAPI backend: registration, login, authenticated farm CRUD, and per-user farm isolation.

## Windows setup (PowerShell)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace SECRET_KEY with a long random value. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For this simple local project, load `.env` into your shell:

```powershell
Get-Content .env | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object { $k,$v = $_ -split '=',2; [Environment]::SetEnvironmentVariable($k,$v,'Process') }
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs and use the interactive API.

## Test steps
1. POST `/auth/register` with `full_name`, `email`, and a 12+ character `password`.
2. POST `/auth/login` with `email` and `password`; copy `access_token`.
3. Click **Authorize** in Swagger, paste the token (Swagger's HTTP Bearer input normally expects the token alone).
4. POST `/farms` with `name`, `region`, `district`, `farm_type` (pond/cage/tank/mixed), `species`.
5. GET `/farms` to see your farms; PUT and DELETE via `/farms/{farm_id}`.

Run tests:

```powershell
pytest -q
```

## PostgreSQL later
Set `DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/aquafarm` and install/start PostgreSQL. Use Alembic migrations before production.

## Important limitations
This is a backend-only development starter, **not production ready**. It lacks email verification, password resets, rate limiting, audit trails, production migrations, backups, billing, refresh tokens, staff roles, and a mobile UI. Do not expose it publicly until those are addressed. Deleting a farm is permanent in this prototype; use soft deletion for commercial operation.
