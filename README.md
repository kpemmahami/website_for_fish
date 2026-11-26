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

## Deploy the backend on Render with Supabase

Set Render's root directory to `backend` and runtime to Python. Use
`pip install -r requirements.txt` as the build command and
`uvicorn app.main:app --host 0.0.0.0 --port "$PORT"` as the start command.
Render supplies `PORT`. The health-check path is `/health`.

In Render's environment settings, set:

- `DATABASE_URL` to the Session pooler URI from Supabase's Connect panel.
  Use port `5432` and the username displayed by Supabase. URL-encode any
  reserved characters in the password. The app selects Psycopg 3 for
  `postgresql://` and `postgres://` URIs.
- `SECRET_KEY` to the existing signing key for this deployment. Keep its
  value in the deployment environment.

Both the API and Alembic add `sslmode=require` to Supabase URLs that omit
it. To verify the server identity as well as encrypt the connection,
provide the Supabase CA file on the host and add
`sslmode=verify-full&sslrootcert=/absolute/path/to/supabase-ca.crt` to the
URL. Locally, an unset `DATABASE_URL` still selects SQLite. On Render,
an unset or SQLite URL fails at startup to prevent accidental use of
an ephemeral database.

For the Render static site, set the build-time variable
`VITE_API_BASE_URL` to the backend's public HTTPS URL without a trailing
`/api`. The AquaFarm Render frontend origin is allowed by default. To allow
additional frontend origins, set `CORS_ALLOWED_ORIGINS` on the backend
to a comma-separated list of exact origins without paths. Rebuild the static site after setting the variable. If the frontend
uses a same-origin `/api/*` rewrite or the local Vite proxy, leave the
frontend variable unset. After deployment, `GET /ready` checks database
connectivity and the registration tables without writing a record.

Run migrations explicitly from `backend` in a secure shell configured with
the target database URL and the deployment signing key. Check the target,
take a backup if it contains records, and run one upgrade process:

```sh
python -m alembic heads
python -m alembic current
python -m alembic upgrade head
python -m alembic current
```

Use Render's pre-deploy command for the upgrade where available. On the
Free plan, run it separately from a trusted workstation or CI runner with
access to the Session pooler before deploying the web service. Application
startup never runs migrations or copies local data.

The backend tests default to an isolated SQLite file. To test PostgreSQL,
set `AQUAFARM_TEST_POSTGRES_URL` to a **new, empty loopback PostgreSQL
database** named `aquafarm_test_*`, using the `postgresql+psycopg://`
scheme, then run `python -m pytest -q` from `backend`.

## Important limitations
This is a backend-only development starter, **not production ready**. It lacks email verification, password resets, rate limiting, audit trails, production migrations, backups, billing, refresh tokens, staff roles, and a mobile UI. Do not expose it publicly until those are addressed. Deleting a farm is permanent in this prototype; use soft deletion for commercial operation.


## Farmer, institution, and administrator access

From the backend directory, load the same environment used by the API. Before an
upgrade, make a SQLite backup of the database identified by `DATABASE_URL` using
SQLite's backup API. Apply the migration and run the first administrator setup on
the server console:

```powershell
python -m alembic upgrade head
python -m tools.setup_admin
```

The setup prompts for the first administrator's name, an unused email address,
and a password. It can succeed only once per database. The former
`AQUAFARM_PLATFORM_ADMIN_EMAIL` setting has no effect. In the web app, choose
**Platform administrator** to sign in. Open **Invite an administrator** to
generate a token bound to an unused email address. Share the token privately
with the invitee, who can redeem it under **Accept an invitation**. Tokens expire
after 24 hours and can be redeemed once.

Choose **Farmer** for farmer registration and **Bank or financial institution**
to create a separate account and submit an institution for approval. Existing
accounts retain their original credentials and memberships. Institution
owners can assign staff roles through the institution portal. Staff with farmer
accounts can reach their institution workspace after signing in as farmers.

| Access | Actions |
| --- | --- |
| Farmer | Submit applications for owned farms with explicit report-sharing consent and view their own applications and loans |
| Verified institution member | View applications, shared evidence, and loans scoped to their institution |
| Institution owner | Manage staff, appraise applications, open loan accounts, and record transactions |
| Institution reviewer | Appraise applications and open loan accounts |
| Institution officer | Record disbursements and repayments |
| Platform administrator | Approve or reject pending institutions and invite administrators |

## Isolated local test portal

Use separate PowerShell terminals with the project virtual environment active.

From `backend`, set the local test environment and seed the designated SQLite database.

```powershell
$env:AQUAFARM_ENV = 'local-test'
$env:DATABASE_URL = 'sqlite:///./aquafarm.local-test.db'
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED = 'false'
$env:AQUAFARM_LOAN_REMINDERS_ENABLED = 'false'
$env:AQUAFARM_EVIDENCE_DIR = Join-Path (Get-Location).Path 'private_evidence\local-test'
python -m tools.seed_local_test_accounts
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

From `frontend`, run `npm.cmd run dev -- --mode local-test --configLoader runner`
and open `http://127.0.0.1:5174/`. Select Platform administrator, Farmer, or
Bank or financial institution and enter the corresponding local test username
`admin`, `farmer`, or `bank`. Rerunning the seed command leaves existing test
accounts and passwords intact and reports conflicting accounts.

For simulated SMS in the isolated local portal, set
`$env:AQUAFARM_LOCAL_TEST_SMS = '1'` in the backend terminal before starting
Uvicorn. Request a code normally and enter `000000` for initial phone
verification or institution SMS sign-in and first-time password setup. This
setting is restricted to the designated local SQLite test database and
does not apply to platform administrator or phone replacement verification.

For Android emulator signup testing, set
`$env:AQUAFARM_LOCAL_TEST_AUTO_APPROVE = '1'` in the isolated backend terminal
before starting Uvicorn. In the debug app, set the backend address to
`http://10.0.2.2:8001`. New farmer and processor registrations can open the
workspace immediately. Use fictional account details. Existing pending accounts
keep their approval status. Hosted signup is unaffected.

## Institution staff invitations

Verified institution owners can use Institution Portal > Institution Management >
Staff Management to invite new or existing users. Existing users respond after
signing into their own account. In the isolated test portal, invitation creation
or resend shows an activation link to the owner.

For email delivery, configure the backend with a trusted HTTPS
AQUAFARM_STAFF_PORTAL_URL and AQUAFARM_STAFF_SMTP_HOST and
AQUAFARM_STAFF_SMTP_FROM. The default STARTTLS port is 587 and can be overridden
with AQUAFARM_STAFF_SMTP_PORT. If the SMTP server requires authentication, set
AQUAFARM_STAFF_SMTP_USERNAME and AQUAFARM_STAFF_SMTP_PASSWORD server-side.

## Interface development standard

Give each page one primary purpose. Use concise module landings with links to dedicated entry, configuration, status, history and analytics views. Reuse existing histories and authoritative status fields, and distinguish overlapping views without duplicating records. Keep relevant actions discoverable with consistent terminology, back navigation and accessible responsive controls. Preserve form data after failed saves and protect unsaved changes where applicable. Refresh affected records and counts after confirmed mutations. Enforce account permissions and tenant boundaries in the backend, preserve existing data and links, and verify web and native mobile behavior separately.

See [Phase 1D audit and acceptance checklist](PHASE_1D_CHECKLIST.md).

See the [master completion checklist](MASTER_COMPLETION_CHECKLIST.md) for the consolidated prompt audit and open work across phases.
