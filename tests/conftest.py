import asyncio
import os
from typing import Generator
from unittest.mock import Mock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.postgres import get_session
from app.config.settings import Settings
from app.main import proclogic
from app.models.base import Base
from app.util.clerk import AuthUser

# Test database URL
TEST_DATABASE_URL = "sqlite:///:memory:"

# Override settings for testing
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["PUBPROC_CLIENT_ID"] = "test-client"
os.environ["PUBPROC_CLIENT_SECRET"] = "test-secret"
os.environ["PUBPROC_SERVER"] = "https://test.server.com"
os.environ["PUBPROC_TOKEN_URL"] = "https://test.server.com/token"
os.environ["CLERK_SECRET_KEY"] = "test-clerk-key"
os.environ["STRIPE_SECRET_KEY"] = "test-stripe-key"
os.environ["STRIPE_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["POSTGRES_CON_URL"] = TEST_DATABASE_URL
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def engine():
    """Create a test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database session override."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    proclogic.dependency_overrides[get_session] = override_get_db
    with TestClient(proclogic) as test_client:
        yield test_client
    proclogic.dependency_overrides.clear()


@pytest.fixture
def mock_auth_user():
    """Create a mock authenticated user."""
    return AuthUser(
        id="test-user-id", email="test@company.com", first_name="Test", last_name="User"
    )


@pytest.fixture
def mock_redis_client(mocker):
    """Mock Redis client."""
    mock_redis = mocker.patch("app.config.redis.get_redis_client")
    mock_client = Mock()
    mock_redis.return_value = mock_client
    return mock_client


@pytest.fixture
def mock_openai_client(mocker):
    """Mock OpenAI client."""
    mock_client = Mock()
    mocker.patch("app.ai.openai.get_openai_client", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_clerk(mocker):
    """Mock Clerk authentication."""
    from app.util.clerk import get_auth_user

    mock_user = AuthUser(
        id="test-user-id", email="test@company.com", first_name="Test", last_name="User"
    )
    mocker.patch("app.util.clerk.get_auth_user", return_value=mock_user)
    return mock_user
