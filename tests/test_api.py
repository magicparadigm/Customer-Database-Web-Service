from app import crud
from app.schemas import CustomerCreate

PAYLOAD = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "company": "Analytical Engines",
}


def test_create_returns_201_and_the_record(auth_client):
    response = auth_client.post("/api/customers", json=PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert body["id"] > 0


def test_create_rejects_a_duplicate_email_with_409(auth_client):
    auth_client.post("/api/customers", json=PAYLOAD)
    response = auth_client.post("/api/customers", json={**PAYLOAD, "first_name": "Someone"})
    assert response.status_code == 409


def test_create_rejects_a_malformed_email(auth_client):
    response = auth_client.post("/api/customers", json={**PAYLOAD, "email": "not-an-email"})
    assert response.status_code == 422


def test_list_is_paginated(auth_client, db_session):
    for i in range(5):
        crud.create_customer(
            db_session,
            CustomerCreate(first_name="A", last_name=f"N{i}", email=f"a{i}@example.com"),
        )

    body = auth_client.get("/api/customers?page=1&page_size=2").json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2


def test_list_honours_search(auth_client, db_session):
    crud.create_customer(
        db_session,
        CustomerCreate(first_name="Ada", last_name="Lovelace", email="ada@example.com"),
    )
    crud.create_customer(
        db_session,
        CustomerCreate(first_name="Bob", last_name="Smith", email="bob@example.com"),
    )

    body = auth_client.get("/api/customers?search=lovelace").json()
    assert body["total"] == 1
    assert body["items"][0]["first_name"] == "Ada"


def test_get_unknown_id_returns_404(auth_client):
    assert auth_client.get("/api/customers/9999").status_code == 404


def test_patch_updates_only_supplied_fields(auth_client):
    created = auth_client.post("/api/customers", json=PAYLOAD).json()

    response = auth_client.patch(
        f"/api/customers/{created['id']}", json={"phone": "555-0100"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["phone"] == "555-0100"
    assert body["company"] == "Analytical Engines"


def test_delete_removes_the_record(auth_client):
    created = auth_client.post("/api/customers", json=PAYLOAD).json()

    assert auth_client.delete(f"/api/customers/{created['id']}").status_code == 204
    assert auth_client.get(f"/api/customers/{created['id']}").status_code == 404


def test_openapi_schema_is_served(auth_client):
    schema = auth_client.get("/openapi.json").json()
    assert "/api/customers" in schema["paths"]
