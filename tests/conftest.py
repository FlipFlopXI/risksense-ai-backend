import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


def validate_test_database_url() -> str:
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not test_url:
        raise pytest.UsageError("TEST_DATABASE_URL is required; refusing to use the application database.")
    try:
        parsed = make_url(test_url)
    except Exception:
        raise pytest.UsageError("Invalid test database URL.") from None
    if parsed.database != "risksense_test":
        raise pytest.UsageError("TEST_DATABASE_URL must target the risksense_test database.")
    if parsed.get_backend_name() != "postgresql" or parsed.host not in ("localhost", "127.0.0.1", "::1"):
        raise pytest.UsageError("Tests require local PostgreSQL; remote hosts are forbidden.")
    if parsed.query:
        raise pytest.UsageError("Test database URL connection overrides are forbidden.")
    return test_url


TEST_DATABASE_URL = validate_test_database_url()
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"
os.environ["ENVIRONMENT"] = "test"


def confirm_test_database() -> None:
    engine = create_engine(validate_test_database_url(), connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            if connection.scalar(text("select current_database()")) != "risksense_test":
                raise pytest.UsageError("Unexpected database; refusing test operations.")
    except Exception:
        raise pytest.UsageError("Could not confirm local risksense_test; no migrations executed.") from None
    finally:
        engine.dispose()

from app.core.dependencies import get_database  # noqa: E402
from app.main import app  # noqa: E402


def alembic_config() -> Config:
    config = Config("alembic.ini")
    return config


def reset_test_schema() -> None:
    """Drop and recreate only public in the explicitly validated test database."""
    validate_test_database_url()
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            current_database = connection.scalar(text("select current_database()"))
            if current_database != "risksense_test":
                raise pytest.UsageError(
                    f"Refusing schema reset for unexpected database {current_database!r}."
                )
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    confirm_test_database()
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture()
def db(migrated_database):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    def override_db():
        yield db
    app.dependency_overrides[get_database] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
