from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


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

    page_size: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
