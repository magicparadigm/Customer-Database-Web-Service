from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_api_caller
from app.db import get_db
from app.schemas import NameVerificationRequest, NameVerificationResult

router = APIRouter(
    prefix="/api/verify",
    tags=["verification"],
    dependencies=[Depends(get_api_caller)],
)


@router.post("", response_model=NameVerificationResult)
def verify_customer_name(
    data: NameVerificationRequest, db: Session = Depends(get_db)
) -> NameVerificationResult:
    """Exact, case-insensitive full-name lookup for the DocuSign data-verification app.

    Always 200: "no such customer" is a verification result, not an HTTP error.
    A name shared by several customers can't be tied to one person, so it is
    reported as not found rather than guessing. An inactive customer is found
    but not verified.
    """
    matches = crud.find_customers_by_full_name(db, data.full_name)
    if len(matches) != 1:
        return NameVerificationResult(found=False, verified=False)

    customer = matches[0]
    return NameVerificationResult(
        found=True,
        verified=customer.is_active,
        id=customer.id,
        email=customer.email,
        company=customer.company,
    )
