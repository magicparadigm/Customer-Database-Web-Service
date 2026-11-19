import pytest

from app.config import settings

PAGES = [
    ("/terms-of-service", "Terms of Service"),
    ("/privacy-policy", "Privacy Policy"),
    ("/support", "Support"),
]


@pytest.mark.parametrize(("path", "heading"), PAGES)
def test_page_is_public_and_renders(client, path, heading):
    """DocuSign links to these from the app manifest; they must not require sign-in."""
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert "text/html" in response.headers["content-type"]


@pytest.mark.parametrize(("path", "_"), PAGES)
def test_page_shows_no_staff_navigation(client, path, _):
    assert "All customers" not in client.get(path).text


def test_pages_link_to_each_other(client):
    assert 'href="/support"' in client.get("/terms-of-service").text
    assert 'href="/support"' in client.get("/privacy-policy").text


def test_support_shows_the_configured_address(client, monkeypatch):
    monkeypatch.setattr(settings, "support_email", "help@example.com")
    assert 'href="mailto:help@example.com"' in client.get("/support").text


def test_support_without_an_address_falls_back_to_generic_text(client, monkeypatch):
    monkeypatch.setattr(settings, "support_email", "")
    text = client.get("/support").text
    assert "mailto:" not in text
    assert "administrator" in text


def test_support_address_is_escaped(client, monkeypatch):
    monkeypatch.setattr(settings, "support_email", '"><script>alert(1)</script>')
    assert "<script>alert(1)</script>" not in client.get("/support").text
