import pytest

from app import crud
from app.routers.api_connected_fields import NOT_VERIFIED_REASON
from app.schemas import CustomerCreate

BASE = "/api/connected-fields"


def add(db, first, last, email, *, company=None, active=True):
    return crud.create_customer(
        db,
        CustomerCreate(
            first_name=first, last_name=last, email=email, company=company, is_active=active
        ),
    )


def verify(client, full_name, *, type_name="customer", key="k-1"):
    return client.post(
        f"{BASE}/verify",
        json={"typeName": type_name, "idempotencyKey": key, "data": {"full_name": full_name}},
    )


@pytest.mark.parametrize("path", ["type-names", "type-definitions", "verify"])
def test_every_action_requires_authentication(client, path):
    assert client.post(f"{BASE}/{path}", json={}).status_code == 401


# --- Get Type Names -------------------------------------------------------------


def test_type_names_lists_the_customer_type(auth_client):
    body = auth_client.post(f"{BASE}/type-names", json={}).json()
    assert [t["typeName"] for t in body["typeNames"]] == ["customer"]
    assert body["typeNames"][0]["label"]


# --- Get Type Definitions ---------------------------------------------------------


def test_type_definition_is_a_verifiable_concept_with_one_required_field(auth_client):
    body = auth_client.post(f"{BASE}/type-definitions", json={"typeNames": ["customer"]}).json()

    assert body["errors"] == []
    (decl,) = body["declarations"]
    assert decl["$class"] == "concerto.metamodel@1.0.0.ConceptDeclaration"
    assert decl["name"] == "customer"
    assert "VerifiableType" in [d["name"] for d in decl["decorators"]]

    (prop,) = decl["properties"]
    assert prop["name"] == "full_name"
    assert prop["$class"] == "concerto.metamodel@1.0.0.StringProperty"
    assert prop["isOptional"] is False
    assert "IsRequiredForVerifyingType" in [d["name"] for d in prop["decorators"]]


def test_type_definition_has_no_crud_decorators(auth_client):
    body = auth_client.post(f"{BASE}/type-definitions", json={"typeNames": ["customer"]}).json()
    (decl,) = body["declarations"]
    names = [d["name"] for d in decl["decorators"]]
    names += [d["name"] for p in decl["properties"] for d in p["decorators"]]
    assert "Crud" not in names


def test_unknown_type_is_reported_in_errors_not_as_an_http_error(auth_client):
    response = auth_client.post(
        f"{BASE}/type-definitions", json={"typeNames": ["customer", "invoice"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["declarations"]) == 1
    assert body["errors"][0]["typeName"] == "invoice"
    assert body["errors"][0]["code"] == "unknown"


# --- Verify -----------------------------------------------------------------------


def test_matching_active_customer_is_verified_with_details_in_passthrough(auth_client, db_session):
    ada = add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    response = verify(auth_client, "Ada Lovelace")

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["verifyResponseMessage"]
    assert "verifyFailureReason" not in body
    assert body["passthroughResponseData"] == {
        "found": True,
        "id": ada.id,
        "email": "ada@example.com",
        "company": "Analytical Engines",
    }


def test_verify_ignores_case_and_extra_whitespace(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert verify(auth_client, "  aDA   LOVELACE ").json()["verified"] is True


def test_unknown_name_fails_verification_with_a_200(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")

    response = verify(auth_client, "Grace Hopper")

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is False
    assert body["verifyFailureReason"] == NOT_VERIFIED_REASON
    assert body["verificationResultCode"] == "NOT_FOUND"
    assert body["passthroughResponseData"] == {"found": False}


def test_partial_name_does_not_verify(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert verify(auth_client, "Ada").json()["verified"] is False


def test_inactive_customer_is_not_verified(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", active=False)

    body = verify(auth_client, "Ada Lovelace").json()

    assert body["verified"] is False
    assert body["verificationResultCode"] == "INACTIVE"
    assert body["passthroughResponseData"]["found"] is True


def test_ambiguous_name_is_not_verified(auth_client, db_session):
    add(db_session, "Sam", "Lee", "sam1@example.com")
    add(db_session, "Sam", "Lee", "sam2@example.com")

    body = verify(auth_client, "Sam Lee").json()

    assert body["verified"] is False
    assert body["verificationResultCode"] == "AMBIGUOUS"
    assert body["passthroughResponseData"] == {"found": False}


def test_signer_sees_the_same_reason_whatever_the_cause(auth_client, db_session):
    """The signer-visible text must not reveal whether a record exists or is inactive."""
    add(db_session, "Ina", "Active", "ina@example.com", active=False)
    add(db_session, "Sam", "Lee", "sam1@example.com")
    add(db_session, "Sam", "Lee", "sam2@example.com")

    reasons = {
        verify(auth_client, name).json()["verifyFailureReason"]
        for name in ("Nobody Here", "Ina Active", "Sam Lee")
    }

    assert reasons == {NOT_VERIFIED_REASON}


def test_same_idempotency_key_gives_the_same_answer(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    first = verify(auth_client, "Ada Lovelace", key="retry-1").json()
    second = verify(auth_client, "Ada Lovelace", key="retry-1").json()
    assert first == second


# --- Errors use DocuSign's 400/404 shape, never 422 -------------------------------


def test_unknown_type_name_is_404_with_code_and_message(auth_client):
    response = verify(auth_client, "Ada Lovelace", type_name="invoice")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["message"]


@pytest.mark.parametrize(
    "payload",
    [
        {"typeName": "customer", "idempotencyKey": "k", "data": {}},
        {"typeName": "customer", "idempotencyKey": "k", "data": {"full_name": "   "}},
        {"typeName": "customer", "idempotencyKey": "k", "data": {"full_name": 42}},
    ],
)
def test_missing_or_bad_full_name_is_400(auth_client, payload):
    response = auth_client.post(f"{BASE}/verify", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"typeName": "customer", "data": {"full_name": "Ada"}},  # no idempotencyKey
        {"typeName": "customer", "idempotencyKey": "k"},  # no data
    ],
)
def test_malformed_body_is_400_not_422(auth_client, payload):
    response = auth_client.post(f"{BASE}/verify", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_unauthenticated_malformed_body_is_still_401(client):
    assert client.post(f"{BASE}/verify", json={}).status_code == 401


def test_other_routes_keep_the_default_422(auth_client):
    assert auth_client.post("/api/verify", json={}).status_code == 422
