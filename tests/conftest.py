import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.db import Base, get_db
from app.main import app
from app.models import User

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def db_session():
    """A fresh in-memory database per test.

    StaticPool keeps every connection pointed at the same in-memory database,
    which otherwise vanishes when a connection closes.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def user(db_session) -> User:
    staff = User(
        username="staffer",
        email="staffer@example.com",
        hashed_password=hash_password(TEST_PASSWORD),
    )
    db_session.add(staff)
    db_session.commit()
    return staff


@pytest.fixture
def client(db_session):
    """Anonymous client wired to the test database."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client, user):
    """Client with a real session cookie, obtained by logging in."""
    response = client.post(
        "/login",
        data={"username": user.username, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, "login fixture failed to authenticate"
    return client
