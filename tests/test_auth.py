from app.auth import authenticate_user, hash_password, verify_password
from app.models import User
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


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_login_with_bad_password_reports_an_error(client, user):
    response = client.post(
        "/login", data={"username": user.username, "password": "wrong"}
    )
    assert response.status_code == 401
    assert "Incorrect username or password" in response.text


def test_login_success_redirects_and_sets_cookie(client, user):
    response = client.post(
        "/login",
        data={"username": user.username, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/customers"
    assert "cdws_session" in response.cookies


def test_login_honours_a_relative_next_url(client, user):
    response = client.post(
        "/login",
        data={"username": user.username, "password": TEST_PASSWORD, "next": "/customers/new"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/customers/new"


def test_login_ignores_an_offsite_next_url(client, user):
    response = client.post(
        "/login",
        data={"username": user.username, "password": TEST_PASSWORD,
              "next": "https://evil.example.com/steal"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/customers", "open redirect must be blocked"


def test_protected_page_redirects_anonymous_browser_to_login(client):
    response = client.get("/customers", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_protected_api_returns_401_not_a_redirect(client):
    response = client.get("/api/customers", follow_redirects=False)
    assert response.status_code == 401


def test_logout_clears_the_session(auth_client):
    assert auth_client.get("/customers", follow_redirects=False).status_code == 200

    auth_client.post("/logout", follow_redirects=False)

    after = auth_client.get("/customers", follow_redirects=False)
    assert after.status_code == 303


def test_session_pointing_at_a_deleted_user_is_rejected(auth_client, db_session, user):
    db_session.delete(user)
    db_session.commit()

    response = auth_client.get("/customers", follow_redirects=False)
    assert response.status_code == 303
