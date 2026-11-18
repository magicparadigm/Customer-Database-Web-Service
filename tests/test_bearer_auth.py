import httpx
import pytest

from app import google_token
from app.config import settings
from app.google_token import (
    GoogleTokenCheckUnavailable,
    InvalidGoogleToken,
    verify_api_token,
)

CLIENT_ID = "our-client.apps.googleusercontent.com"
BEARER = {"Authorization": "Bearer ya29.fake"}


def good_info(**overrides) -> dict:
    return {
        "aud": CLIENT_ID,
        "email": "dana@example.com",
        "email_verified": "true",
        "expires_in": "3000",
        **overrides,
    }


@pytest.fixture
def bearer_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "api_allowed_email_domains", "example.com")
    monkeypatch.setattr(settings, "api_allowed_emails", "")


@pytest.fixture
def tokeninfo(monkeypatch):
    """Control what Google's tokeninfo 'returns'. Set .result to a dict or exception."""

    class Stub:
        result: dict | Exception = good_info()

    def fake(_token):
        if isinstance(Stub.result, Exception):
            raise Stub.result
        return Stub.result

    monkeypatch.setattr(google_token, "_fetch_tokeninfo", fake)
    return Stub


def test_valid_token_from_allowed_domain_can_call_the_api(client, bearer_configured, tokeninfo):
    assert client.get("/api/customers", headers=BEARER).status_code == 200


def test_token_issued_to_another_client_is_rejected(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(aud="someone-elses-client.apps.googleusercontent.com")
    response = client.get("/api/customers", headers=BEARER)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_account_outside_allowed_domain_is_rejected(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(email="mallory@gmail.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_lookalike_domain_is_not_a_suffix_match(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(email="mallory@evilexample.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_subdomain_is_not_implicitly_allowed(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(email="mallory@sub.example.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_individually_allowed_email_outside_the_domain_list(
    client, bearer_configured, tokeninfo, monkeypatch
):
    monkeypatch.setattr(settings, "api_allowed_emails", "Contractor@Gmail.com")
    tokeninfo.result = good_info(email="contractor@gmail.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 200


def test_email_match_is_case_insensitive(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(email="Dana@EXAMPLE.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 200


def test_unverified_email_is_rejected(client, bearer_configured, tokeninfo):
    tokeninfo.result = good_info(email_verified="false")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_token_without_email_scope_is_rejected(client, bearer_configured, tokeninfo):
    info = good_info()
    del info["email"], info["email_verified"]
    tokeninfo.result = info
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_token_google_rejects_gets_401(client, bearer_configured, tokeninfo):
    tokeninfo.result = InvalidGoogleToken("expired")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_google_outage_fails_closed_with_503(client, bearer_configured, tokeninfo):
    tokeninfo.result = GoogleTokenCheckUnavailable("down")
    assert client.get("/api/customers", headers=BEARER).status_code == 503


def test_empty_bearer_token_is_rejected(client, bearer_configured, tokeninfo):
    response = client.get("/api/customers", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_no_allowlist_configured_allows_nobody(client, bearer_configured, tokeninfo, monkeypatch):
    monkeypatch.setattr(settings, "api_allowed_email_domains", "")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_bearer_is_refused_when_no_client_id_is_configured(client, tokeninfo, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "api_allowed_email_domains", "example.com")
    assert client.get("/api/customers", headers=BEARER).status_code == 401


def test_bad_bearer_is_401_even_with_a_valid_session(
    auth_client, bearer_configured, tokeninfo
):
    tokeninfo.result = InvalidGoogleToken("nope")
    assert auth_client.get("/api/customers", headers=BEARER).status_code == 401


def test_session_auth_still_works_without_an_authorization_header(auth_client):
    assert auth_client.get("/api/customers").status_code == 200


def test_bearer_does_not_unlock_the_html_pages(client, bearer_configured, tokeninfo):
    response = client.get("/customers", headers=BEARER, follow_redirects=False)
    assert response.status_code == 303


# --- the real tokeninfo HTTP call, with the network stubbed -----------------------


def _stub_httpx(monkeypatch, response=None, error=None):
    def fake_get(url, **kwargs):
        if error:
            raise error
        return response

    monkeypatch.setattr(google_token.httpx, "get", fake_get)


def _response(status, **kwargs):
    return httpx.Response(status, request=httpx.Request("GET", google_token.TOKENINFO_URL), **kwargs)


def test_tokeninfo_400_means_invalid_token(monkeypatch):
    _stub_httpx(monkeypatch, _response(400, json={"error": "invalid_token"}))
    with pytest.raises(InvalidGoogleToken):
        google_token._fetch_tokeninfo("t")


def test_tokeninfo_5xx_means_unavailable_not_invalid(monkeypatch):
    _stub_httpx(monkeypatch, _response(503))
    with pytest.raises(GoogleTokenCheckUnavailable):
        google_token._fetch_tokeninfo("t")


def test_tokeninfo_network_error_means_unavailable(monkeypatch):
    _stub_httpx(monkeypatch, error=httpx.ConnectTimeout("slow"))
    with pytest.raises(GoogleTokenCheckUnavailable):
        google_token._fetch_tokeninfo("t")


def test_verify_returns_the_callers_email(bearer_configured, tokeninfo):
    assert verify_api_token("t").email == "dana@example.com"
