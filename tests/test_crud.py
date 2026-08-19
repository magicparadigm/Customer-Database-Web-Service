import pytest

from app import crud
from app.schemas import CustomerCreate, CustomerUpdate


def make(email="jo@example.com", **kw) -> CustomerCreate:
    return CustomerCreate(
        first_name=kw.pop("first_name", "Jo"),
        last_name=kw.pop("last_name", "Bloggs"),
        email=email,
        **kw,
    )


def test_create_and_get(db_session):
    created = crud.create_customer(db_session, make())
    assert created.id is not None
    assert crud.get_customer(db_session, created.id).email == "jo@example.com"


def test_duplicate_email_rejected(db_session):
    crud.create_customer(db_session, make())
    with pytest.raises(crud.DuplicateEmailError):
        crud.create_customer(db_session, make(first_name="Other"))


def test_duplicate_email_is_case_insensitive(db_session):
    crud.create_customer(db_session, make(email="Jo@Example.com"))
    with pytest.raises(crud.DuplicateEmailError):
        crud.create_customer(db_session, make(email="jo@example.com"))


def test_update_changes_only_supplied_fields(db_session):
    customer = crud.create_customer(db_session, make(company="Acme"))
    crud.update_customer(db_session, customer, CustomerUpdate(phone="555-0100"))
    assert customer.phone == "555-0100"
    assert customer.company == "Acme", "unsupplied fields must be left alone"


def test_update_can_clear_a_field(db_session):
    customer = crud.create_customer(db_session, make(company="Acme"))
    crud.update_customer(db_session, customer, CustomerUpdate(company=None))
    assert customer.company is None


def test_update_to_an_existing_email_is_rejected(db_session):
    crud.create_customer(db_session, make(email="first@example.com"))
    second = crud.create_customer(db_session, make(email="second@example.com"))
    with pytest.raises(crud.DuplicateEmailError):
        crud.update_customer(db_session, second, CustomerUpdate(email="first@example.com"))


def test_update_keeping_own_email_is_allowed(db_session):
    customer = crud.create_customer(db_session, make(email="mine@example.com"))
    crud.update_customer(
        db_session, customer, CustomerUpdate(email="mine@example.com", phone="555-1234")
    )
    assert customer.phone == "555-1234"


def test_delete(db_session):
    customer = crud.create_customer(db_session, make())
    customer_id = customer.id
    crud.delete_customer(db_session, customer)
    assert crud.get_customer(db_session, customer_id) is None


def test_search_matches_name_email_and_company(db_session):
    crud.create_customer(db_session, make(email="ada@example.com", first_name="Ada",
                                          last_name="Lovelace", company="Analytical"))
    crud.create_customer(db_session, make(email="bob@other.com", first_name="Bob",
                                          last_name="Smith", company="Widgets"))

    for term, expected in [("lovelace", 1), ("ADA", 1), ("analytical", 1),
                           ("other.com", 1), ("example", 1), ("z", 0)]:
        items, total, _ = crud.list_customers(db_session, search=term)
        assert total == expected, f"search {term!r} returned {total}, expected {expected}"
        assert len(items) == expected


def test_pagination_splits_results_and_reports_pages(db_session):
    for i in range(7):
        crud.create_customer(db_session, make(email=f"c{i}@example.com", last_name=f"N{i}"))

    page1, total, total_pages = crud.list_customers(db_session, page=1, page_size=3)
    page3, _, _ = crud.list_customers(db_session, page=3, page_size=3)

    assert total == 7
    assert total_pages == 3
    assert len(page1) == 3
    assert len(page3) == 1
    assert {c.id for c in page1}.isdisjoint({c.id for c in page3})


def test_include_inactive_false_filters_them_out(db_session):
    crud.create_customer(db_session, make(email="on@example.com"))
    crud.create_customer(db_session, make(email="off@example.com", is_active=False))

    _, total_all, _ = crud.list_customers(db_session)
    _, total_active, _ = crud.list_customers(db_session, include_inactive=False)

    assert total_all == 2
    assert total_active == 1
