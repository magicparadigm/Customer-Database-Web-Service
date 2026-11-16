from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SESSION_USER_KEY, find_user_for_oauth_identity, oauth, safe_next
from app.config import settings
from app.db import get_db
from app.templating import templates

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_google_configured() -> None:
    if not settings.google_oauth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND)


def _callback_url(request: Request) -> str:
    """Build the callback URL, forcing https in production.

    Railway terminates TLS in front of the app; without trusting its proxy
    headers, `request.url_for` sees the plain-http request it forwards and
    would hand Google a redirect_uri that doesn't match what's registered
    in the OAuth client config.
    """
    url = request.url_for("google_oauth_callback")
    if settings.environment == "production":
        url = url.replace(scheme="https")
    return str(url)


@router.get("/google/login")
async def google_login(request: Request, next: str | None = None):
    _require_google_configured()
    request.session["oauth_next"] = safe_next(next)
    return await oauth.google.authorize_redirect(request, _callback_url(request))


@router.get("/google/callback", name="google_oauth_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    _require_google_configured()
    next_url = request.session.pop("oauth_next", "/customers")

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next_url,
                "error": "Google sign-in failed. Try again.",
                "google_oauth_enabled": True,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    claims = token.get("userinfo") or {}
    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = bool(claims.get("email_verified"))

    user = None
    if subject and email:
        user = find_user_for_oauth_identity(
            db,
            provider="google",
            subject=subject,
            email=email,
            email_verified=email_verified,
        )

    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next_url,
                "error": "No staff account matches that Google account. "
                "Ask an admin to create one first.",
                "google_oauth_enabled": True,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # New session id on privilege change, to blunt session fixation.
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    return RedirectResponse(next_url, status_code=status.HTTP_303_SEE_OTHER)
