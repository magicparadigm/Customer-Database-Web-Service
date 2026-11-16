from app.auth import find_user_for_oauth_identity


def test_links_existing_user_by_verified_email_on_first_login(db_session, user):
    linked = find_user_for_oauth_identity(
        db_session,
        provider="google",
        subject="google-sub-123",
        email=user.email.upper(),  # case-insensitive match
        email_verified=True,
    )
    assert linked is not None
    assert linked.id == user.id
    assert user.oauth_provider == "google"
    assert user.oauth_subject == "google-sub-123"


def test_reuses_the_link_on_subsequent_logins(db_session, user):
    first = find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=True
    )
    second = find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=True
    )
    assert first is not None and second is not None
    assert first.id == second.id == user.id


def test_rejects_unverified_email(db_session, user):
    result = find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=False
    )
    assert result is None
    assert user.oauth_provider is None


def test_rejects_when_no_user_matches_the_email(db_session):
    result = find_user_for_oauth_identity(
        db_session,
        provider="google",
        subject="sub-1",
        email="nobody@example.com",
        email_verified=True,
    )
    assert result is None


def test_rejects_disabled_account_even_with_matching_email(db_session, user):
    user.is_active = False
    db_session.commit()

    result = find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=True
    )
    assert result is None


def test_rejects_disabled_account_after_being_linked(db_session, user):
    find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=True
    )
    user.is_active = False
    db_session.commit()

    result = find_user_for_oauth_identity(
        db_session, provider="google", subject="sub-1", email=user.email, email_verified=True
    )
    assert result is None


def test_login_page_omits_google_button_when_unconfigured(client):
    response = client.get("/login")
    assert "Sign in with Google" not in response.text


def test_google_routes_404_when_oauth_is_not_configured(client):
    assert client.get("/auth/google/login", follow_redirects=False).status_code == 404
    assert client.get("/auth/google/callback", follow_redirects=False).status_code == 404
