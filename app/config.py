from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

_DEV_SECRET_KEY = "dev-only-insecure-change-me"


def _split_csv(raw: str) -> list[str]:
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """Application settings, read from the environment or a .env file."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Customer Database"
    environment: str = "development"
    debug: bool = True

    # Swapping to Postgres or SQL Server means changing only this value.
    database_url: str = f"sqlite:///{BASE_DIR / 'customers.db'}"
    sql_echo: bool = False  # Log every statement. Noisy; for debugging only.

    # Signs the session cookie. Must be overridden outside development.
    secret_key: str = _DEV_SECRET_KEY
    session_cookie_name: str = "cdws_session"
    session_max_age: int = 60 * 60 * 8  # 8 hours

    page_size: int = 25

    # "Sign in with Google" is offered only when both are set; unset leaves
    # password login as the only option.
    google_client_id: str | None = None
    google_client_secret: str | None = None

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    # Google accounts allowed to call /api with a Bearer token. Comma-separated.
    # Both empty means Bearer access is refused for everyone. GOOGLE_CLIENT_ID is
    # the audience a token must have been issued to.
    api_allowed_email_domains: str = ""
    api_allowed_emails: str = ""

    # Shown on the public support page. Blank shows the page without an address.
    support_email: str = ""

    @property
    def allowed_api_domains(self) -> frozenset[str]:
        return frozenset(_split_csv(self.api_allowed_email_domains))

    @property
    def allowed_api_emails(self) -> frozenset[str]:
        return frozenset(_split_csv(self.api_allowed_emails))

    @model_validator(mode="after")
    def _reject_dev_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.secret_key == _DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is still the development placeholder. Set a real "
                "SECRET_KEY before running with ENVIRONMENT=production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
