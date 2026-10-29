import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_environment_variables_override_dotenv(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("TRACERAG_ENVIRONMENT=development\n", encoding="utf-8")
    monkeypatch.setenv("TRACERAG_ENVIRONMENT", "production")
    assert Settings(_env_file=dotenv).environment == "production"


@pytest.mark.parametrize("value", ["staging", "", "prod"])
def test_invalid_environment_is_rejected(value, monkeypatch):
    monkeypatch.setenv("TRACERAG_ENVIRONMENT", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_app_name_is_rejected(monkeypatch):
    monkeypatch.setenv("TRACERAG_APP_NAME", "   ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "values",
    [
        {"chunk_size": 10, "chunk_overlap": 10},
        {"max_upload_bytes": 0},
        {"max_pdf_pages": 0},
        {"parse_timeout_seconds": 0},
        {"database_url": "sqlite:///test.db"},
    ],
)
def test_invalid_ingestion_settings(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
