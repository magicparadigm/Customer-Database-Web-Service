from app.auth import authenticate_user, hash_password, verify_password
from tests.conftest import TEST_PASSWORD


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password", "password must not be stored in the clear"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_authenticate_user_accepts_valid_credentials(db_session, user):
    assert authenticate_user(db_session, user.username, TEST_PASSWORD) is not None


def test_authenticate_user_rejects_bad_password(db_session, user):
    assert authenticate_user(db_session, user.username, "nope") is None


def test_authenticate_user_rejects_unknown_username(db_session):
    assert authenticate_user(db_session, "ghost", "whatever") is None


def test_authenticate_user_rejects_disabled_account(db_session, user):
    user.is_active = False
    db_session.commit()
    assert authenticate_user(db_session, user.username, TEST_PASSWORD) is None


def test_protected_page_without_credentials_gets_a_basic_auth_challenge(client):
    response = client.get("/customers", follow_redirects=False)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_protected_api_without_credentials_gets_a_basic_auth_challenge(client):
    response = client.get("/api/customers", follow_redirects=False)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_correct_credentials_grant_access(client, user):
    client.auth = (user.username, TEST_PASSWORD)
    response = client.get("/customers", follow_redirects=False)
    assert response.status_code == 200


def test_wrong_password_is_rejected(client, user):
    client.auth = (user.username, "wrong")
    response = client.get("/customers", follow_redirects=False)
    assert response.status_code == 401


def test_credentials_for_a_deleted_user_are_rejected(auth_client, db_session, user):
    assert auth_client.get("/customers", follow_redirects=False).status_code == 200

    db_session.delete(user)
    db_session.commit()

    response = auth_client.get("/customers", follow_redirects=False)
    assert response.status_code == 401


def test_credentials_for_a_disabled_user_are_rejected(auth_client, db_session, user):
    assert auth_client.get("/customers", follow_redirects=False).status_code == 200

    user.is_active = False
    db_session.commit()

    response = auth_client.get("/customers", follow_redirects=False)
    assert response.status_code == 401
