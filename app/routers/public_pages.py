"""Public pages that DocuSign and the public may open without signing in.

These are linked from the DocuSign app manifest (terms, privacy, support), so they must
stay reachable anonymously. They contain no customer data.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.templating import templates

router = APIRouter(tags=["public"], include_in_schema=False)


@router.get("/terms-of-service", response_class=HTMLResponse)
def terms_of_service(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})


@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


@router.get("/support", response_class=HTMLResponse)
def support(request: Request):
    return templates.TemplateResponse(
        request, "support.html", {"support_email": settings.support_email}
    )
