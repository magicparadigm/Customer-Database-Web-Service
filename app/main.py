from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticatedError, login_redirect
from app.config import settings
from app.routers import (
    api_connected_fields,
    api_customers,
    api_verify,
    oauth,
    web_auth,
    web_customers,
)

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


@app.exception_handler(RequestValidationError)
async def _bad_request_for_docusign(request: Request, exc: RequestValidationError):
    """DocuSign's contract allows only 400/404/500 for unprocessable calls, not 422.

    Scoped to the connected-fields routes; every other route keeps FastAPI's 422.
    """
    if request.url.path.startswith("/api/connected-fields"):
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'][1:])}: {err['msg']}"
            for err in exc.errors()
        )
        return JSONResponse(
            {"code": "BAD_REQUEST", "message": f"Invalid request body. {problems}"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await request_validation_exception_handler(request, exc)


app.include_router(web_auth.router)
app.include_router(oauth.router)
app.include_router(web_customers.router)
app.include_router(api_customers.router)
app.include_router(api_verify.router)
app.include_router(api_connected_fields.router)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/customers", status_code=status.HTTP_302_FOUND)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}
