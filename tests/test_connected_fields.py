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


def test_type_definition_is_a_verifiable_concept_with_full_name_required(auth_client):
    body = auth_client.post(f"{BASE}/type-definitions", json={"typeNames": ["customer"]}).json()

    assert body["errors"] == []
    (decl,) = body["declarations"]
    assert decl["$class"] == "concerto.metamodel@1.0.0.ConceptDeclaration"
    assert decl["name"] == "customer"
    assert "VerifiableType" in [d["name"] for d in decl["decorators"]]

    props = {p["name"]: p for p in decl["properties"]}
    assert set(props) == {"full_name", "company"}

    full_name = props["full_name"]
    assert full_name["$class"] == "concerto.metamodel@1.0.0.StringProperty"
    assert full_name["isOptional"] is False
    assert "IsRequiredForVerifyingType" in [d["name"] for d in full_name["decorators"]]


def test_company_is_optional_and_not_required_for_verifying(auth_client):
    body = auth_client.post(f"{BASE}/type-definitions", json={"typeNames": ["customer"]}).json()
    (decl,) = body["declarations"]
    company = next(p for p in decl["properties"] if p["name"] == "company")
    assert company["isOptional"] is True
    assert "IsRequiredForVerifyingType" not in [d["name"] for d in company["decorators"]]


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


# --- Search Records (DataIO) -------------------------------------------------------

CLASS = "com.docusign.connected.data.queries@1.0.0"


def search_query(value="Ada Lovelace", *, field="full_name", operator="EQUALS", **extra):
    query = {
        "$class": f"{CLASS}.Query",
        "attributesToSelect": ["full_name"],
        "from": "customer",
        "queryFilter": {
            "$class": f"{CLASS}.QueryFilter",
            "operation": {
                "$class": f"{CLASS}.ComparisonOperation",
                "leftOperand": {
                    "$class": f"{CLASS}.Operand", "name": field, "type": "STRING",
                    "isLiteral": False,
                },
                "operator": operator,
                "rightOperand": {
                    "$class": f"{CLASS}.Operand", "name": value, "type": "STRING",
                    "isLiteral": True,
                },
            },
        },
    }
    query.update(extra)
    return query


def search(client, query=None, pagination=None):
    return client.post(
        f"{BASE}/search-records",
        json={"query": query or search_query(), "pagination": pagination or {"limit": 5, "skip": 0}},
    )


def test_search_requires_authentication(client):
    assert client.post(f"{BASE}/search-records", json={}).status_code == 401


def test_search_finds_exactly_one_active_match(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    response = search(auth_client, search_query("ada LOVELACE"))

    assert response.status_code == 200
    assert response.json() == {"records": [{"full_name": "Ada Lovelace"}]}


def test_search_never_returns_email_company_or_id(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    query = search_query(attributesToSelect=["full_name", "email", "company", "id"])
    record = search(auth_client, query).json()["records"][0]

    assert record == {"full_name": "Ada Lovelace"}


def test_search_with_no_match_is_empty_records_not_404(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")

    response = search(auth_client, search_query("Grace Hopper"))

    assert response.status_code == 200
    assert response.json() == {"records": []}


def test_search_hides_inactive_and_ambiguous_customers(auth_client, db_session):
    add(db_session, "Ina", "Gone", "ina@example.com", active=False)
    add(db_session, "Sam", "Lee", "sam1@example.com")
    add(db_session, "Sam", "Lee", "sam2@example.com")

    assert search(auth_client, search_query("Ina Gone")).json() == {"records": []}
    assert search(auth_client, search_query("Sam Lee")).json() == {"records": []}


def test_search_agrees_with_verify(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    add(db_session, "Ina", "Gone", "ina@example.com", active=False)

    for name in ("Ada Lovelace", "Ina Gone", "Nobody Here"):
        found = bool(search(auth_client, search_query(name)).json()["records"])
        assert found == verify(auth_client, name).json()["verified"], name


def test_search_page_two_is_empty(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert search(auth_client, pagination={"limit": 5, "skip": 1}).json() == {"records": []}


@pytest.mark.parametrize(
    "query",
    [
        search_query(operator="CONTAINS"),
        search_query(operator="STARTS_WITH"),
        search_query(operator="LIKE"),
        search_query(field="email"),
        {"from": "customer"},  # no filter at all would mean "list everyone"
        {"from": "customer", "queryFilter": {}},
        {"from": "customer", "queryFilter": {"operation": {"operator": "AND"}}},
    ],
)
def test_search_refuses_anything_but_full_name_equals(auth_client, db_session, query):
    add(db_session, "Ada", "Lovelace", "ada@example.com")

    response = search(auth_client, query)

    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_search_refuses_a_filter_that_swaps_field_and_value(auth_client):
    query = search_query()
    op = query["queryFilter"]["operation"]
    op["leftOperand"]["isLiteral"] = True
    assert search(auth_client, query).status_code == 400


def test_search_unknown_type_is_404(auth_client):
    assert search(auth_client, search_query(**{"from": "invoice"})).status_code == 404


def test_search_malformed_body_is_400_not_422(auth_client):
    response = auth_client.post(f"{BASE}/search-records", json={"pagination": {}})
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


# --- Company autofill (suggestions) -------------------------------------------------


def verify_with(client, data):
    return client.post(
        f"{BASE}/verify",
        json={"typeName": "customer", "idempotencyKey": "k-1", "data": data},
    )


def test_verified_customer_gets_company_as_an_autofill_suggestion(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    body = verify(auth_client, "Ada Lovelace").json()

    assert body["verified"] is True
    assert body["suggestions"] == [{"full_name": "Ada Lovelace", "company": "Analytical Engines"}]


def test_suggestion_always_includes_the_required_full_name(auth_client, db_session):
    """DocuSign's contract: a suggestion must carry every required property."""
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    (suggestion,) = verify(auth_client, "Ada Lovelace").json()["suggestions"]

    assert "full_name" in suggestion


def test_suggestion_echoes_the_name_as_typed_not_the_stored_casing(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    (suggestion,) = verify(auth_client, "  ada   LOVELACE ").json()["suggestions"]

    assert suggestion["full_name"] == "ada LOVELACE"  # whitespace tidied, casing untouched


def test_customer_without_a_company_gets_only_the_name_back(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company=None)

    body = verify(auth_client, "Ada Lovelace").json()

    assert body["verified"] is True
    assert body["suggestions"] == [{"full_name": "Ada Lovelace"}]


def test_company_typed_by_the_signer_does_not_decide_the_outcome(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    body = verify_with(
        auth_client, {"full_name": "Ada Lovelace", "company": "Some Other Company"}
    ).json()

    assert body["verified"] is True
    # The stored value is offered, so a wrong entry is corrected by autofill.
    assert body["suggestions"][0]["company"] == "Analytical Engines"


def test_omitting_company_is_fine(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")
    assert verify_with(auth_client, {"full_name": "Ada Lovelace"}).json()["verified"] is True


def test_unverified_results_never_include_suggestions(auth_client, db_session):
    add(db_session, "Ina", "Gone", "ina@example.com", company="Hidden Co", active=False)
    add(db_session, "Sam", "Lee", "sam1@example.com", company="Dup One")
    add(db_session, "Sam", "Lee", "sam2@example.com", company="Dup Two")

    for name in ("Nobody Here", "Ina Gone", "Sam Lee"):
        body = verify(auth_client, name).json()
        assert body["verified"] is False, name
        assert "suggestions" not in body, name
        assert "Hidden Co" not in str(body["verifyFailureReason"]), name


def test_suggestion_exposes_no_email_or_id(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    (suggestion,) = verify(auth_client, "Ada Lovelace").json()["suggestions"]

    assert set(suggestion) <= {"full_name", "company"}
