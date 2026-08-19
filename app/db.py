from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def normalize_database_url(url: str) -> str:
    """Rewrite a bare Postgres URL to name the psycopg driver explicitly.

    Railway (like Heroku before it) hands out `postgres://...` or plain
    `postgresql://...`; SQLAlchemy 2.0 needs the driver in the scheme to pick
    psycopg over the default psycopg2, which isn't installed here.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


_database_url = normalize_database_url(settings.database_url)
_is_sqlite = _database_url.startswith("sqlite")

engine = create_engine(
    _database_url,
    # SQLite refuses cross-thread use by default; FastAPI's threadpool needs it.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Opt-in: SQL_ECHO=true. Tying this to DEBUG floods normal CLI and test output.
    echo=settings.sql_echo,
    future=True,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        """WAL for concurrent reads during writes; foreign keys are off by default."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that always closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
