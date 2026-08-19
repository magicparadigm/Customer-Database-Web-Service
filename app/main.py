from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticatedError, login_redirect
from app.config import settings
from app.routers import api_customers, web_auth, web_customers

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title=settings.app_name,
    description="Customer records over a JSON API and a staff web UI.",
    version="0.1.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.environment == "production",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(NotAuthenticatedError)
async def _redirect_to_login(request: Request, _exc: NotAuthenticatedError):
    """Unauthenticated browser requests land on the login page, not a JSON 401."""
    return login_redirect(request)


app.include_router(web_auth.router)
app.include_router(web_customers.router)
app.include_router(api_customers.router)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/customers", status_code=status.HTTP_302_FOUND)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}
