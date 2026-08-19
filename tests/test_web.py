from app import crud
from app.schemas import CustomerCreate

FORM = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "company": "Analytical Engines",
    "phone": "",
    "street": "",
    "city": "",
    "state": "",
    "postal_code": "",
    "country": "",
    "notes": "",
    "is_active": "1",
}


def add(db, email="ada@example.com", **kw):
    return crud.create_customer(
        db,
        CustomerCreate(
            first_name=kw.pop("first_name", "Ada"),
            last_name=kw.pop("last_name", "Lovelace"),
            email=email,
            **kw,
        ),
    )


def test_list_page_renders_with_no_customers(auth_client):
    response = auth_client.get("/customers")
    assert response.status_code == 200
    assert "No customers yet" in response.text


def test_list_page_shows_a_customer(auth_client, db_session):
    add(db_session)
    response = auth_client.get("/customers")
    assert "Ada Lovelace" in response.text
    assert "ada@example.com" in response.text


def test_search_fragment_is_not_a_full_page(auth_client, db_session):
    add(db_session)
    response = auth_client.get("/customers/search?search=lovelace")
    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "<html" not in response.text.lower(), "fragment must not include the layout"


def test_search_fragment_reports_no_matches(auth_client, db_session):
    add(db_session)
    response = auth_client.get("/customers/search?search=zzzz")
    assert "No customers match" in response.text


def test_create_via_form_redirects_to_the_detail_page(auth_client, db_session):
    response = auth_client.post("/customers", data=FORM, follow_redirects=False)
    assert response.status_code == 303

    _, total, _ = crud.list_customers(db_session)
    assert total == 1
    assert response.headers["location"].startswith("/customers/")


def test_blank_optional_fields_are_stored_as_null(auth_client, db_session):
    auth_client.post("/customers", data=FORM, follow_redirects=False)
    items, _, _ = crud.list_customers(db_session)
    assert items[0].phone is None, "empty form input should be NULL, not an empty string"


def test_create_with_an_invalid_email_rerenders_the_form(auth_client):
    response = auth_client.post(
        "/customers", data={**FORM, "email": "nope"}, follow_redirects=False
    )
    assert response.status_code == 422
    assert "Ada" in response.text, "submitted values should be preserved"


def test_create_with_a_duplicate_email_shows_a_conflict(auth_client, db_session):
    add(db_session)
    response = auth_client.post("/customers", data=FORM, follow_redirects=False)
    assert response.status_code == 409
    assert "already exists" in response.text


def test_unchecked_active_box_marks_the_customer_inactive(auth_client, db_session):
    form = {k: v for k, v in FORM.items() if k != "is_active"}
    auth_client.post("/customers", data=form, follow_redirects=False)
    items, _, _ = crud.list_customers(db_session)
    assert items[0].is_active is False


def test_detail_page_renders(auth_client, db_session):
    customer = add(db_session, company="Analytical Engines")
    response = auth_client.get(f"/customers/{customer.id}")
    assert response.status_code == 200
    assert "ada@example.com" in response.text
    assert "Analytical Engines" in response.text


def test_detail_page_for_a_missing_customer_is_404(auth_client):
    response = auth_client.get("/customers/9999")
    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_edit_form_is_prefilled(auth_client, db_session):
    customer = add(db_session, company="Analytical Engines")
    response = auth_client.get(f"/customers/{customer.id}/edit")
    assert response.status_code == 200
    assert 'value="Analytical Engines"' in response.text


def test_update_via_form_persists(auth_client, db_session):
    customer = add(db_session)
    response = auth_client.post(
        f"/customers/{customer.id}",
        data={**FORM, "phone": "555-0100"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db_session.refresh(customer)
    assert customer.phone == "555-0100"


def test_delete_removes_the_row(auth_client, db_session):
    customer = add(db_session)
    response = auth_client.delete(f"/customers/{customer.id}")
    assert response.status_code == 200
    assert response.text == "", "HTMX swaps the row out with an empty response"
    assert crud.get_customer(db_session, customer.id) is None


def test_root_redirects_to_the_customer_list(auth_client):
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/customers"
