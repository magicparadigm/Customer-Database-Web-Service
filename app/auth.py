from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

SESSION_USER_KEY = "user_id"


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


def login_redirect(request: Request) -> RedirectResponse:
    """Send an unauthenticated browser to /login, remembering where it came from."""
    next_url = request.url.path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    target = "/login" if next_url in ("/", "/login") else f"/login?next={next_url}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
