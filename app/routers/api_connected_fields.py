"""DocuSign Connected Fields app: the four calls DocuSign makes to this service.

DocuSign POSTs to each of these (see docusign-extension/manifest.json). The first three
belong to a Data IO extension, the last to a Connected Fields extension:

* type-names        — which data types exist                       (DataIO...GetTypeNames)
* type-definitions  — the fields of those types, as Concerto JSON  (DataIO...GetTypeDefinitions)
* search-records    — find a record by a filter                    (DataIO...SearchRecords)
* verify            — check one entered value                      (ConnectedFields...Verify)

We expose a single type, `customer`, with a single field, `full_name`. Verification is
the same exact, case-insensitive full-name lookup as POST /api/verify.
"""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_api_caller
from app.db import get_db
from app.models import Customer

router = APIRouter(
    prefix="/api/connected-fields",
    tags=["docusign-connected-fields"],
    dependencies=[Depends(get_api_caller)],
)

TYPE_NAME = "customer"
FIELD_NAME = "full_name"

# Shown to the signer on any failed check. Deliberately identical for "no such
# customer", "several customers" and "inactive customer": the signer is not
# necessarily staff and must not be able to learn which records exist or their
# status. The real reason goes in verificationResultCode, which DocuSign hides.
NOT_VERIFIED_REASON = (
    "We couldn't verify that name. Check that it is spelled the way it appears "
    "on your customer record, then try again."
)

_C = "concerto.metamodel@1.0.0"


def _decorator(name: str, *strings: str) -> dict:
    decorator: dict[str, Any] = {"$class": f"{_C}.Decorator", "name": name}
    if strings:
        decorator["arguments"] = [
            {"$class": f"{_C}.DecoratorString", "value": value} for value in strings
        ]
    return decorator


def _customer_declaration() -> dict:
    """Concerto definition of the `customer` type.

    VerifiableType makes every property a connected field; IsRequiredForVerifyingType
    makes DocuSign wait for full_name before it calls verify. No Crud decorators —
    DocuSign says not to include them for connected fields.
    """
    return {
        "$class": f"{_C}.ConceptDeclaration",
        "name": TYPE_NAME,
        "isAbstract": False,
        "decorators": [_decorator("VerifiableType"), _decorator("Term", "Customer")],
        "properties": [
            {
                "$class": f"{_C}.StringProperty",
                "name": FIELD_NAME,
                "isOptional": False,
                "isArray": False,
                "decorators": [
                    _decorator("IsRequiredForVerifyingType"),
                    _decorator("Term", "Full Name"),
                ],
            }
        ],
    }


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """DocuSign's error shape for actions that cannot be processed."""
    return JSONResponse({"code": code, "message": message}, status_code=status_code)


class TypeDefinitionsRequest(BaseModel):
    typeNames: list[str]


class SearchRequest(BaseModel):
    query: dict[str, Any]
    pagination: dict[str, Any] | None = None


class VerifyRequest(BaseModel):
    typeName: str
    idempotencyKey: str
    data: dict[str, Any]


class VerifyResponse(BaseModel):
    verified: bool
    verifyResponseMessage: str
    verifyFailureReason: str | None = None
    verificationResultCode: str | None = None
    passthroughResponseData: dict[str, Any] | None = None


@router.post("/type-names")
def get_type_names() -> dict:
    return {
        "typeNames": [
            {
                "typeName": TYPE_NAME,
                "label": "Customer",
                "description": "Verifies a full name against the customer database",
            }
        ]
    }


@router.post("/type-definitions")
def get_type_definitions(data: TypeDefinitionsRequest) -> dict:
    declarations = []
    errors = []
    for name in data.typeNames:
        if name == TYPE_NAME:
            declarations.append(_customer_declaration())
        else:
            errors.append(
                {"typeName": name, "code": "unknown", "message": f"Unknown type {name!r}"}
            )
    return {"declarations": declarations, "errors": errors}


@router.post("/verify", response_model=VerifyResponse, response_model_exclude_none=True)
def verify(data: VerifyRequest, db: Session = Depends(get_db)):
    """Exact, case-insensitive full-name check.

    A failed check is a normal 200 with verified=false (DocuSign: "do not return an
    HTTP error" when verification ran). The matched customer's id, email and company
    ride in passthroughResponseData, which DocuSign does not show the signer.

    idempotencyKey is required by the contract but needs no storage here: the lookup
    is a pure read, so DocuSign's retries (which reuse the key) get the same answer.
    """
    if data.typeName != TYPE_NAME:
        return _error(404, "NOT_FOUND", f"Unknown type {data.typeName!r}")

    full_name = data.data.get(FIELD_NAME)
    if not isinstance(full_name, str) or not full_name.strip():
        return _error(400, "BAD_REQUEST", f"data.{FIELD_NAME} is required")

    result_code, customer = _lookup(db, full_name)

    if customer is None:
        return _not_verified(result_code, {"found": False})

    details = {
        "found": True,
        "id": customer.id,
        "email": customer.email,
        "company": customer.company,
    }
    if result_code == "INACTIVE":
        return _not_verified(result_code, details)

    return VerifyResponse(
        verified=True,
        verifyResponseMessage="Name verified.",
        verificationResultCode="VERIFIED",
        passthroughResponseData=details,
    )


def _lookup(db: Session, full_name: str) -> tuple[str, Customer | None]:
    """Shared by verify and search so they can never disagree.

    Returns (code, customer). Codes: VERIFIED, INACTIVE (customer set), NOT_FOUND,
    AMBIGUOUS (customer None — several customers share the name, so it can't be tied
    to one person and is treated as not found).
    """
    matches = crud.find_customers_by_full_name(db, full_name)
    if not matches:
        return "NOT_FOUND", None
    if len(matches) > 1:
        return "AMBIGUOUS", None
    customer = matches[0]
    return ("VERIFIED" if customer.is_active else "INACTIVE"), customer


class _UnsupportedQuery(ValueError):
    pass


def _full_name_from_query(query: dict[str, Any]) -> str:
    """The name in a `full_name EQUALS <literal>` filter.

    That is the only query this service answers. A missing filter or any other field
    or operator is refused rather than approximated, because a looser search would let
    a caller enumerate customers by guessing prefixes.
    """
    unsupported = _UnsupportedQuery(
        f"Only a {FIELD_NAME} EQUALS <value> filter is supported."
    )
    try:
        operation = query["queryFilter"]["operation"]
        left, right = operation["leftOperand"], operation["rightOperand"]
        operator = operation["operator"]
    except (KeyError, TypeError):
        raise unsupported from None

    if (
        operator != "EQUALS"
        or not isinstance(left, dict)
        or not isinstance(right, dict)
        or left.get("name") != FIELD_NAME
        or left.get("isLiteral")
        or not right.get("isLiteral")
        or not isinstance(right.get("name"), str)
    ):
        raise unsupported
    return right["name"]


@router.post("/search-records")
def search_records(data: SearchRequest, db: Session = Depends(get_db)):
    """DataIO Search Records: find the customer whose full_name equals a value.

    Returns at most one record, `{"full_name": ...}`, and only when verify would pass
    (exactly one active customer has that name). No match is `{"records": []}`, never
    a 404, as the contract requires. Email, company and id are not returned here.
    """
    if data.query.get("from") != TYPE_NAME:
        return _error(404, "NOT_FOUND", f"Unknown type {data.query.get('from')!r}")

    try:
        full_name = _full_name_from_query(data.query)
    except _UnsupportedQuery as exc:
        return _error(400, "BAD_REQUEST", str(exc))

    pagination = data.pagination or {}
    skip, limit = pagination.get("skip", 0), pagination.get("limit")
    if (isinstance(skip, int) and skip > 0) or limit == 0:
        return {"records": []}  # the single possible record is on page one only

    result_code, customer = _lookup(db, full_name)
    if result_code != "VERIFIED" or customer is None:
        return {"records": []}

    available = {FIELD_NAME: customer.full_name}
    wanted = data.query.get("attributesToSelect") or [FIELD_NAME]
    record = {k: available[k] for k in wanted if isinstance(k, str) and k in available}
    return {"records": [record]}


def _not_verified(result_code: str, details: dict) -> VerifyResponse:
    return VerifyResponse(
        verified=False,
        verifyResponseMessage="Verification failed.",
        verifyFailureReason=NOT_VERIFIED_REASON,
        verificationResultCode=result_code,
        passthroughResponseData=details,
    )
