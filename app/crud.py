"""Shared data-access and business logic.

Both the JSON API and the HTML routes call into this module, so validation and
business rules live here exactly once and the two surfaces cannot drift.
"""

import math

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Customer
from app.schemas import CustomerCreate, CustomerUpdate


class DuplicateEmailError(ValueError):
    """Raised when an email is already attached to another customer."""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"A customer with email {email!r} already exists.")


def _email_taken(db: Session, email: str, exclude_id: int | None = None) -> bool:
    stmt = select(Customer.id).where(func.lower(Customer.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    return db.scalar(stmt) is not None


def get_customer(db: Session, customer_id: int) -> Customer | None:
    return db.get(Customer, customer_id)


def list_customers(
    db: Session,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int | None = None,
    include_inactive: bool = True,
) -> tuple[list[Customer], int, int]:
    """Return (items, total_matching, total_pages) for one page of results.

    `search` matches first name, last name, email, or company, case-insensitively.
    """
    page_size = page_size or settings.page_size
    page = max(1, page)

    stmt = select(Customer)
    count_stmt = select(func.count()).select_from(Customer)

    if not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))
        count_stmt = count_stmt.where(Customer.is_active.is_(True))

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        condition = or_(
            func.lower(Customer.first_name).like(pattern),
            func.lower(Customer.last_name).like(pattern),
            func.lower(Customer.email).like(pattern),
            func.lower(func.coalesce(Customer.company, "")).like(pattern),
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / page_size))

    stmt = (
        stmt.order_by(Customer.last_name, Customer.first_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt))
    return items, total, total_pages


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    if _email_taken(db, data.email):
        raise DuplicateEmailError(data.email)

    customer = Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session, customer: Customer, data: CustomerUpdate
) -> Customer:
    # exclude_unset only: an explicitly-sent null is a request to clear the field,
    # which is different from omitting it.
    changes = data.model_dump(exclude_unset=True)

    new_email = changes.get("email")
    if new_email and _email_taken(db, new_email, exclude_id=customer.id):
        raise DuplicateEmailError(new_email)

    for field, value in changes.items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, customer: Customer) -> None:
    db.delete(customer)
    db.commit()
