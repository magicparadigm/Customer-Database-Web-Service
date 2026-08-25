from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SESSION_USER_KEY, authenticate_user, safe_next
from app.config import settings
from app.db import get_db
from app.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str | None = None):
    if request.session.get(SESSION_USER_KEY):
        return RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "next": next or "",
            "error": None,
            "google_oauth_enabled": settings.google_oauth_enabled,
        },
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Incorrect username or password.",
                "username": username,
                "google_oauth_enabled": settings.google_oauth_enabled,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # New session id on privilege change, to blunt session fixation.
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    return RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
