from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.google_token import (
    ApiCaller,
    GoogleTokenCheckUnavailable,
    InvalidGoogleToken,
    verify_api_token,
)
from app.models import User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

SESSION_USER_KEY = "user_id"

oauth = OAuth()

if settings.google_oauth_enabled:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Return the user when credentials are valid, else None.

    Always runs a hash comparison so a missing username and a wrong password
    take similar time and cannot be told apart by an observer.
    """
    user = get_user_by_username(db, username)
    if user is None:
        pwd_context.dummy_verify()
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def find_user_for_oauth_identity(
    db: Session, *, provider: str, subject: str, email: str, email_verified: bool
) -> User | None:
    """Match an OAuth identity to an existing staff account, linking it on first use.

    Staff accounts are provisioned out-of-band (`manage.py createuser`); OAuth never
    creates one. A previously-linked (provider, subject) is trusted outright. Otherwise
    the identity's verified email must match exactly one existing, unlinked, active
    user — who then gets linked for next time. Anything else (no match, unverified
    email, inactive account) returns None and the caller rejects the sign-in.
    """
    linked = db.scalar(
        select(User).where(User.oauth_provider == provider, User.oauth_subject == subject)
    )
    if linked is not None:
        return linked if linked.is_active else None

    if not email_verified:
        return None

    candidate = db.scalar(
        select(User).where(
            func.lower(User.email) == email.lower(), User.oauth_provider.is_(None)
        )
    )
    if candidate is None or not candidate.is_active:
        return None

    candidate.oauth_provider = provider
    candidate.oauth_subject = subject
    db.commit()
    db.refresh(candidate)
    return candidate


class NotAuthenticatedError(Exception):
    """Raised for unauthenticated browser requests; handled by a redirect."""


def _wants_json(request: Request) -> bool:
    """The /api surface gets a 401; the HTML surface gets sent to the login page.

    Decided by path, not by the Accept header — the routers are already split
    cleanly, and header sniffing misjudges clients that omit Accept.
    """
    return request.url.path.startswith("/api")


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        if _wants_json(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        raise NotAuthenticatedError

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        # Stale cookie pointing at a deleted or disabled account.
        request.session.clear()
        if _wants_json(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        raise NotAuthenticatedError

    return user


def get_api_caller(
    request: Request, db: Session = Depends(get_db)
) -> User | ApiCaller:
    """Authenticate a /api request by Google Bearer token or, failing that, session.

    A request that presents a Bearer token is judged on that token alone: a bad
    token is a 401 even if a valid session cookie rides along. No Authorization
    header at all falls through to the normal session check.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return get_current_user(request, db)

    challenge = {"WWW-Authenticate": "Bearer"}
    token = token.strip()
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid bearer token", headers=challenge
        )
    try:
        return verify_api_token(token)
    except InvalidGoogleToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid bearer token", headers=challenge
        ) from None
    except GoogleTokenCheckUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Token verification unavailable"
        ) from None


def safe_next(next_url: str | None) -> str:
    """Only allow same-site relative redirects, never an absolute URL."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/customers"


def login_redirect(request: Request) -> RedirectResponse:
    """Send an unauthenticated browser to /login, remembering where it came from."""
    next_url = request.url.path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    target = "/login" if next_url in ("/", "/login") else f"/login?next={next_url}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
