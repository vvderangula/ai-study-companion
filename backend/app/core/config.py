"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "AI Study Companion"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    # Security
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    admin_emails: Annotated[list[str], NoDecode] = Field(default=[])

    # Database
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "studymate"

    # Background work (in-process thread pool; no external queue for the MVP)
    job_backend: str = "thread"  # thread | inline
    job_max_attempts: int = 3
    job_workers: int = 2

    # File storage
    upload_dir: str = "storage/uploads"
    max_upload_size_mb: int = 25

    # AI providers. Order of preference; each is tried in turn on failure.
    ai_provider_order: Annotated[list[str], NoDecode] = Field(default=["groq", "gemini"])  # or ["fake"]
    ai_timeout_seconds: float = 90.0

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_primary: str = "llama-3.3-70b-versatile"
    groq_model_fast: str = "llama-3.1-8b-instant"
    groq_model_vision: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model_primary: str = "gemini-2.5-flash"
    gemini_model_fast: str = "gemini-2.5-flash-lite"
    gemini_model_vision: str = "gemini-2.5-flash"

    # Embeddings (local, no key)
    embedding_backend: str = "fastembed"  # fastembed | hash
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # Retrieval / chunking
    chunk_size: int = 900
    chunk_overlap: int = 150
    retrieval_top_k: int = 6
    evidence_min_similarity: float = 0.62

    # Learning model
    mastery_threshold_strong: float = 0.75
    mastery_threshold_weak: float = 0.5

    @field_validator("cors_origins", "admin_emails", "ai_provider_order", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
