"""
src/config/settings.py
──────────────────────
Pydantic-settings based config — reads from environment / .env file.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3-5-sonnet"
    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_embedding_model: str = "models/embedding-001"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimension: int = 1536

    # Ollama (local fallback — no API key needed)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://hiring_user:hiring_pass@localhost:5432/hiring_ai"
    database_url_sync: str = "postgresql://hiring_user:hiring_pass@localhost:5432/hiring_ai"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Email ─────────────────────────────────────────────────────────────────
    email_backend: str = "smtp"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""
    hr_email: str = ""
    from_email: str = "noreply@hiring.ai"

    # ── Google Calendar ───────────────────────────────────────────────────────
    google_credentials_path: str = "./config/google_credentials.json"
    google_calendar_id: str = "primary"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # ── Pipeline Thresholds ───────────────────────────────────────────────────
    max_jd_revisions: int = 5
    max_repost_attempts: int = 3
    shortlist_top_n: int = 5
    resume_score_threshold: float = 20.0
    resume_intake_dir: str = "./data/resumes/"

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:5173"
    secret_key: str = "change-me-in-production"

    # ── Job Platforms ─────────────────────────────────────────────────────────
    linkedin_access_token: str = "your_linkedin_access_token"
    linkedin_company_urn:  str = ""


settings = Settings()
