from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_current_user
from app.db import get_db
from app.schemas import CustomerCreate, CustomerPage, CustomerRead, CustomerUpdate

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=CustomerPage)
def list_customers(
    search: str | None = Query(default=None, description="Matches name, email, or company"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> CustomerPage:
    items, total, total_pages = crud.list_customers(
        db,
        search=search,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
    )
    return CustomerPage(
        items=[CustomerRead.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerRead:
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerRead.model_validate(customer)


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    data: CustomerCreate, db: Session = Depends(get_db)
) -> CustomerRead:
    try:
        customer = crud.create_customer(db, data)
    except crud.DuplicateEmailError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CustomerRead.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int, data: CustomerUpdate, db: Session = Depends(get_db)
) -> CustomerRead:
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    try:
        customer = crud.update_customer(db, customer, data)
    except crud.DuplicateEmailError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CustomerRead.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    customer = crud.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    crud.delete_customer(db, customer)
