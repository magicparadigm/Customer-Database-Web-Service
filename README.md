# Customer Database Web Service

A staff-facing customer database. The same records are available two ways:

- **Web UI** at `/customers` — server-rendered pages with HTMX for live search and inline delete
- **JSON API** at `/api/customers` — full CRUD, documented at `/docs`

Both surfaces call the same logic in [`app/crud.py`](app/crud.py), so business rules exist in
exactly one place. All routes require a signed-in staff user.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"

cp .env.example .env            # then edit SECRET_KEY
alembic upgrade head
python manage.py createuser     # prompts for username, email, password
```

Want staff to be able to sign in with Google instead of typing a password? Set
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env` — see the comments in
[`.env.example`](.env.example) for how to get them and which redirect URI to register.
Leave them unset and the login page only shows the password form.

Generate a real secret key for anything but local development:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 and sign in.

Want sample data to look at? `python manage.py seed --count 30`.

## Admin commands

| Command | Purpose |
|---|---|
| `python manage.py createuser` | Create a staff login (prompts for password if `--password` is omitted) |
| `python manage.py setpassword` | Reset an existing login's password (prompts if `--password` is omitted) |
| `python manage.py listusers` | List staff logins |
| `python manage.py seed --count N` | Insert sample customers |

## Tests

```bash
pytest                                  # 57 tests
pytest --cov=app --cov-report=term-missing
```

Tests run against a fresh in-memory SQLite database per test — they never touch `customers.db`.

## Layout

```
app/
  main.py          App, session middleware, router wiring
  config.py        Settings from .env
  db.py            Engine, session factory, get_db dependency
  models.py        Customer, User
  schemas.py       Pydantic request/response models
  crud.py          Shared data-access and business logic
  auth.py          Password hashing, sessions, get_current_user, OAuth identity linking
  routers/         api_customers, web_customers, web_auth, oauth
  templates/       Jinja2 pages and HTMX fragments (_row, _rows)
  static/          style.css, vendored htmx.min.js
alembic/           Migrations
tests/             pytest suite
```

## Deploying to Railway

The app is deployed via GitHub auto-deploy, with Railway Postgres replacing SQLite (Railway's
filesystem doesn't persist SQLite files across deploys).

1. Push this repo to GitHub.
2. Railway: **New Project → Deploy from GitHub repo**, pick this repo.
3. Railway: **+ New → Database → PostgreSQL** in the same project. Railway injects `DATABASE_URL`
   into the web service automatically.
4. Web service → **Variables**, set:
   - `ENVIRONMENT=production`
   - `DEBUG=false`
   - `SECRET_KEY=` output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`
     (the app refuses to start in production with the placeholder key)
   - Optionally `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` to enable Google sign-in — register
     `https://<your-app>.up.railway.app/auth/google/callback` as an authorized redirect URI for
     that OAuth client first.
5. Deploy. The [`Procfile`](Procfile)'s `release:` line runs `alembic upgrade head` before the
   new `web:` process takes traffic — check the build log for it.
6. Create the first login against the live database, one time, via the Railway CLI:
   ```bash
   railway login
   railway link            # pick this project
   railway run python manage.py createuser
   ```
7. Visit the assigned `*.up.railway.app` domain and sign in.

[`railway.toml`](railway.toml) points Railway's healthcheck at `/healthz` and restarts on failure.

## Notes on the design

**SQLite is the starting point, not a commitment.** Everything goes through SQLAlchemy and
Alembic, and only `DATABASE_URL` names the backend. Moving to Postgres or SQL Server means
changing that value and reviewing the migrations — install the matching driver
(`psycopg`, `pyodbc`) and run `alembic upgrade head` against the new database.

**Sessions, not JWT.** The UI is a browser tool, so it uses a signed HTTP-only session cookie —
simpler and revocable. Passwords are hashed with Argon2.

**OAuth links accounts, it doesn't create them.** Signing in with Google matches the verified
email from Google against an existing `users` row and links it (`oauth_provider`/`oauth_subject`)
on first use — it never provisions a new staff account on its own. Access is still controlled by
who an admin ran `manage.py createuser` for; OAuth just adds a second way to prove you're them.

**Auth failures differ by surface.** Anything under `/api` gets a `401`; everything else
redirects to `/login?next=…`. That split is by path, deliberately, rather than by sniffing the
`Accept` header.

**Bearer tokens are for machines, and they're narrow.** `/api/*` also accepts
`Authorization: Bearer <google-access-token>`. The token must have been issued to
`GOOGLE_CLIENT_ID` (checked via Google's tokeninfo endpoint), carry a verified email, and
that email must be on `API_ALLOWED_EMAIL_DOMAINS` / `API_ALLOWED_EMAILS`. Bearer callers
are not `users` rows and never touch the session. The DocuSign Connected Fields extension
(`docusign-extension/`) calls `/api/connected-fields/*`; its verify step is an exact,
case-insensitive full-name match, and inactive or ambiguous matches come back unverified.
`POST /api/verify` is the same lookup as a plain JSON endpoint.

**HTMX returns fragments.** `/customers/search` renders `_rows.html` alone, with no page layout,
so search results swap in without a reload. Delete swaps out a single `<tr>`.

## Not built yet

CSV import/export, audit logging, role-based permissions, and password reset. Each is a clean
addition on top of what's here.
