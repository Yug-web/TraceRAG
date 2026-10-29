from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Validate process configuration once when the application is created."""

    model_config = SettingsConfigDict(
        env_prefix="TRACERAG_",
        env_file=".env",
        extra="ignore",
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="TraceRAG", min_length=1)
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_pdf_pages: int = Field(default=100, ge=1, le=1000)
    max_text_chars: int = Field(default=2_000_000, ge=1, le=10_000_000)
    max_page_stream_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    parse_timeout_seconds: int = Field(default=20, ge=1, le=120)
    chunk_size: int = Field(default=1000, ge=1, le=10000)
    chunk_overlap: int = Field(default=200, ge=0)
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", min_length=1, max_length=255
    )
    embedding_revision: str = Field(
        default="1110a243fdf4706b3f48f1d95db1a4f5529b4d41", pattern=r"^[0-9a-f]{40}$"
    )
    embedding_dimensions: int = Field(default=384, ge=1, le=4096)
    embedding_max_tokens: int = Field(default=256, ge=8, le=8192)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_local_files_only: bool = False
    llm_provider: Literal["gemini"] = "gemini"
    gemini_api_key: SecretStr | None = None
    llm_model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=128)
    llm_timeout_seconds: int = Field(default=30, ge=1, le=120)
    llm_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    qa_context_chars: int = Field(default=12000, ge=1000, le=40000)

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                url = make_url(value.get_secret_value())
                valid = url.drivername == "postgresql+psycopg" and bool(url.database)
            except Exception:
                valid = False
            if not valid:
                raise ValueError("Use a postgresql+psycopg URL with a database name")
        return value

    @model_validator(mode="after")
    def validate_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self
