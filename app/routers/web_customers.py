from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import CustomerCreate, CustomerUpdate
from app.templating import templates

router = APIRouter(
    prefix="/customers",
    tags=["web"],
    dependencies=[Depends(get_current_user)],
)


def _blank_to_none(value: str | None) -> str | None:
    """An empty form field means 'no value', not an empty string."""
    if value is None:
        return None
    value = value.strip()
    return value or None


async def _form_payload(request: Request) -> dict:
    form = await request.form()
    return {
        "first_name": (form.get("first_name") or "").strip(),
        "last_name": (form.get("last_name") or "").strip(),
        "email": (form.get("email") or "").strip(),
        "phone": _blank_to_none(form.get("phone")),
        "company": _blank_to_none(form.get("company")),
        "street": _blank_to_none(form.get("street")),
        "city": _blank_to_none(form.get("city")),
        "state": _blank_to_none(form.get("state")),
        "postal_code": _blank_to_none(form.get("postal_code")),
        "country": _blank_to_none(form.get("country")),
        "notes": _blank_to_none(form.get("notes")),
        "is_active": form.get("is_active") is not None,
    }


def _friendly_errors(exc: ValidationError) -> dict[str, str]:
    """Map pydantic errors to {field: message} for inline display."""
    errors: dict[str, str] = {}
    for err in exc.errors():
        field = str(err["loc"][0]) if err["loc"] else "__all__"
        errors.setdefault(field, err["msg"])
    return errors


@router.get("", response_class=HTMLResponse)
def list_page(
    request: Request,
    search: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total, total_pages = crud.list_customers(db, search=search, page=page)
    return templates.TemplateResponse(
        request,
        "customers/list.html",
        {
            "customers": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "user": user,
        },
    )


@router.get("/search", response_class=HTMLResponse)
def search_fragment(
    request: Request,
    search: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """HTMX target: returns table rows only, not a full page."""
    items, total, total_pages = crud.list_customers(db, search=search, page=page)
    return templates.TemplateResponse(
        request,
        "customers/_rows.html",
        {
            "customers": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "customers/form.html",
        {"customer": None, "values": {"is_active": True}, "errors": {}, "user": user},
    )


@router.post("")
async def create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = await _form_payload(request)
    try:
        data = CustomerCreate(**payload)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "customers/form.html",
            {"customer": None, "values": payload, "errors": _friendly_errors(exc), "user": user},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        customer = crud.create_customer(db, data)
    except crud.DuplicateEmailError as exc:
        return templates.TemplateResponse(
            request,
            "customers/form.html",
            {"customer": None, "values": payload, "errors": {"email": str(exc)}, "user": user},
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse(
        f"/customers/{customer.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{customer_id}", response_class=HTMLResponse)
def detail_page(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"user": user}, status_code=status.HTTP_404_NOT_FOUND
        )
    return templates.TemplateResponse(
        request, "customers/detail.html", {"customer": customer, "user": user}
    )


@router.get("/{customer_id}/edit", response_class=HTMLResponse)
def edit_form(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"user": user}, status_code=status.HTTP_404_NOT_FOUND
        )
    return templates.TemplateResponse(
        request,
        "customers/form.html",
        {"customer": customer, "values": customer, "errors": {}, "user": user},
    )


@router.post("/{customer_id}")
async def update(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"user": user}, status_code=status.HTTP_404_NOT_FOUND
        )

    payload = await _form_payload(request)
    try:
        data = CustomerUpdate(**payload)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "customers/form.html",
            {"customer": customer, "values": payload, "errors": _friendly_errors(exc), "user": user},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        crud.update_customer(db, customer, data)
    except crud.DuplicateEmailError as exc:
        return templates.TemplateResponse(
            request,
            "customers/form.html",
            {"customer": customer, "values": payload, "errors": {"email": str(exc)}, "user": user},
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse(
        f"/customers/{customer_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.delete("/{customer_id}")
def delete(customer_id: int, db: Session = Depends(get_db)):
    """HTMX removes the row on an empty 200 response."""
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    crud.delete_customer(db, customer)
    return Response(status_code=status.HTTP_200_OK)
