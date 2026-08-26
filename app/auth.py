from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

security = HTTPBasic()


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


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Every route depends on this. A missing Authorization header is already
    rejected by the HTTPBasic security scheme itself, with the browser-prompting
    401 + WWW-Authenticate header; this only needs to handle bad credentials.
    """
    user = authenticate_user(db, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user
