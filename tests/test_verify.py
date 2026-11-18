from app import crud
from app.schemas import CustomerCreate


def add(db, first, last, email, *, company=None, active=True):
    return crud.create_customer(
        db,
        CustomerCreate(
            first_name=first, last_name=last, email=email, company=company, is_active=active
        ),
    )


def verify(client, name):
    return client.post("/api/verify", json={"full_name": name})


def test_requires_authentication(client):
    assert verify(client, "Ada Lovelace").status_code == 401


def test_exact_match_returns_id_email_and_company(auth_client, db_session):
    ada = add(db_session, "Ada", "Lovelace", "ada@example.com", company="Analytical Engines")

    response = verify(auth_client, "Ada Lovelace")

    assert response.status_code == 200
    assert response.json() == {
        "found": True,
        "verified": True,
        "id": ada.id,
        "email": "ada@example.com",
        "company": "Analytical Engines",
    }


def test_match_ignores_case(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert verify(auth_client, "ADA lovelace").json()["found"] is True


def test_surrounding_and_repeated_whitespace_is_normalized(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert verify(auth_client, "  Ada    Lovelace ").json()["found"] is True


def test_unknown_name_is_found_false_with_200(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")

    response = verify(auth_client, "Grace Hopper")

    assert response.status_code == 200
    assert response.json() == {
        "found": False,
        "verified": False,
        "id": None,
        "email": None,
        "company": None,
    }


def test_partial_names_do_not_match(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    for partial in ("Ada", "Lovelace", "Ad Lovelace", "Ada Love", "Lovelace Ada", "Ada%"):
        assert verify(auth_client, partial).json()["found"] is False, partial


def test_like_wildcards_are_not_interpreted(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com")
    assert verify(auth_client, "A_a L%").json()["found"] is False


def test_inactive_customer_is_found_but_not_verified(auth_client, db_session):
    add(db_session, "Ada", "Lovelace", "ada@example.com", active=False)

    body = verify(auth_client, "Ada Lovelace").json()

    assert body["found"] is True
    assert body["verified"] is False
    assert body["email"] == "ada@example.com"


def test_ambiguous_name_is_reported_as_not_found(auth_client, db_session):
    add(db_session, "Sam", "Lee", "sam1@example.com")
    add(db_session, "Sam", "Lee", "sam2@example.com")

    body = verify(auth_client, "sam lee").json()

    assert body["found"] is False
    assert body["verified"] is False
    assert body["email"] is None


def test_blank_name_is_rejected(auth_client):
    assert verify(auth_client, "   ").status_code == 422
    assert verify(auth_client, "").status_code == 422


def test_missing_field_is_rejected(auth_client):
    assert auth_client.post("/api/verify", json={}).status_code == 422


def test_overlong_name_is_rejected(auth_client):
    assert verify(auth_client, "x" * 500).status_code == 422
