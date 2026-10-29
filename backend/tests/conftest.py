import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app


class RedactedDatabaseURL(str):
    def __repr__(self) -> str:
        return "<test database URL redacted>"


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TRACERAG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TRACERAG_TEST_DATABASE_URL for PostgreSQL integration tests")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Test database must use postgresql+psycopg and a name ending in _test")
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    command.check(config)
    return RedactedDatabaseURL(url)


@pytest.fixture
def db_engine(database_url):
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents CASCADE"))
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents CASCADE"))
    engine.dispose()


@pytest.fixture
def document_client(database_url, db_engine):
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        environment="test",
        chunk_size=12,
        chunk_overlap=3,
    )
    with TestClient(create_app(settings)) as client:
        yield client
