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
    hr_email: str = ""
    from_email: str = "noreply@hiring.ai"

    # ── Google Calendar ───────────────────────────────────────────────────────
    google_credentials_path: str = "./config/google_credentials.json"
    google_calendar_id: str = "primary"

    # ── Pipeline Thresholds ───────────────────────────────────────────────────
    max_jd_revisions: int = 5
    max_repost_attempts: int = 3
    shortlist_top_n: int = 5
    resume_score_threshold: float = 65.0
    resume_intake_dir: str = "./data/resumes/"

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me-in-production"


settings = Settings()
