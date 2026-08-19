from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SESSION_USER_KEY, authenticate_user
from app.db import get_db
from app.templating import templates

router = APIRouter(tags=["auth"])


def _safe_next(next_url: str | None) -> str:
    """Only allow same-site relative redirects, never an absolute URL."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/customers"


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str | None = None):
    if request.session.get(SESSION_USER_KEY):
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "login.html", {"next": next or "", "error": None}
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
            {"next": next, "error": "Incorrect username or password.", "username": username},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # New session id on privilege change, to blunt session fixation.
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
