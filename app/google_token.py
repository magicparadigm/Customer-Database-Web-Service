"""Validate Google OAuth access tokens presented as Bearer credentials on /api.

Google access tokens are opaque, so they are checked against Google's tokeninfo
endpoint. Beyond "Google says it is live", two checks carry the security:

* audience — the token must have been issued to *our* OAuth client. Without
  this, a token minted for any other app would be accepted here.
* allowlist — the account's verified email must be on the configured domain or
  email list. With nothing configured, nobody is allowed (fail closed).
"""

from dataclasses import dataclass

import httpx

from app.config import settings

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_TIMEOUT_SECONDS = 5.0


class InvalidGoogleToken(Exception):
    """Not acceptable: malformed, expired, wrong audience, or account not allowed."""


class GoogleTokenCheckUnavailable(Exception):
    """Google could not be reached to check the token. Callers must fail closed."""


@dataclass(frozen=True)
class ApiCaller:
    """A Bearer-authenticated caller. Not a staff `User` row; identified by email."""

    email: str


def _fetch_tokeninfo(access_token: str) -> dict:
    try:
        response = httpx.get(
            TOKENINFO_URL,
            params={"access_token": access_token},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GoogleTokenCheckUnavailable("could not reach Google") from exc

    if response.status_code == 400:  # Google's answer for bad or expired tokens.
        raise InvalidGoogleToken("Google rejected the token")
    if response.status_code != 200:
        raise GoogleTokenCheckUnavailable(f"tokeninfo returned {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise GoogleTokenCheckUnavailable("tokeninfo returned a non-JSON body") from exc


def _is_allowed(email: str) -> bool:
    if email in settings.allowed_api_emails:
        return True
    # Exact domain compare on the part after the last "@" — never a suffix match,
    # which "evilexample.com" would pass for "example.com".
    return email.rpartition("@")[2] in settings.allowed_api_domains


def verify_api_token(access_token: str) -> ApiCaller:
    if not settings.google_client_id:
        raise InvalidGoogleToken("Bearer access is not configured")

    info = _fetch_tokeninfo(access_token)

    if info.get("aud") != settings.google_client_id:
        raise InvalidGoogleToken("token was issued to a different client")

    email = str(info.get("email") or "").strip().lower()
    if not email or str(info.get("email_verified")).lower() != "true":
        raise InvalidGoogleToken("token carries no verified email")

    if not _is_allowed(email):
        raise InvalidGoogleToken("account is not on the allowed list")

    return ApiCaller(email=email)
