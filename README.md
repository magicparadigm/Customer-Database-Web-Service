# Customer Database Web Service

A staff-facing customer database. The same records are available two ways:

- **Web UI** at `/customers` — server-rendered pages with HTMX for live search and inline delete
- **JSON API** at `/api/customers` — full CRUD, documented at `/docs`

Both surfaces call the same logic in [`app/crud.py`](app/crud.py), so business rules exist in
exactly one place. All routes require HTTP Basic Auth against a staff user.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"

cp .env.example .env
alembic upgrade head
python manage.py createuser     # prompts for username, email, password
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 — your browser will prompt for the username/password from
`createuser`.

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
pytest                                  # 46 tests
pytest --cov=app --cov-report=term-missing
```

Tests run against a fresh in-memory SQLite database per test — they never touch `customers.db`.

## Layout

```
app/
  main.py          App, router wiring
  config.py        Settings from .env
  db.py            Engine, session factory, get_db dependency
  models.py        Customer, User
  schemas.py       Pydantic request/response models
  crud.py          Shared data-access and business logic
  auth.py          Password hashing, HTTP Basic Auth, get_current_user
  routers/         api_customers, web_customers
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
5. Deploy. [`railway.toml`](railway.toml)'s `preDeployCommand` runs `alembic upgrade head` before
   the new instance takes traffic — check the deploy log for it.
6. Create the first login against the live database, one time, via the Railway CLI:
   ```bash
   railway login
   railway link            # pick this project
   railway ssh python manage.py createuser
   ```
7. Visit the assigned `*.up.railway.app` domain — your browser will prompt for those credentials.

[`railway.toml`](railway.toml) points Railway's healthcheck at `/healthz` and restarts on failure.

## Notes on the design

**SQLite is the starting point, not a commitment.** Everything goes through SQLAlchemy and
Alembic, and only `DATABASE_URL` names the backend. Moving to Postgres or SQL Server means
changing that value and reviewing the migrations — install the matching driver
(`psycopg`, `pyodbc`) and run `alembic upgrade head` against the new database.

**HTTP Basic Auth, not sessions.** Every request carries an `Authorization: Basic` header,
checked against Argon2-hashed passwords on each call — there's no server-side session state to
manage or expire. The trade-off: no custom login page (the browser's native credential prompt
handles that) and no real server-side logout — a browser holds onto credentials for an origin
until it's closed. `get_current_user` (in [`app/auth.py`](app/auth.py)) is the single dependency
both the web UI and the JSON API rely on, so a request either surface can't authenticate is
rejected the same way: `401` plus a `WWW-Authenticate: Basic` header.

**HTMX returns fragments.** `/customers/search` renders `_rows.html` alone, with no page layout,
so search results swap in without a reload. Delete swaps out a single `<tr>`.

## Not built yet

CSV import/export, audit logging, role-based permissions, and password reset. Each is a clean
addition on top of what's here.
