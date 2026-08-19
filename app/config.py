from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

_DEV_SECRET_KEY = "dev-only-insecure-change-me"


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
