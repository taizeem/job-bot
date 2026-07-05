"""
Application configuration via Pydantic BaseSettings.

Loads settings from environment variables and ``.env`` file.
All paths are resolved relative to the project root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Job Bot application.

    Values are loaded from environment variables first, then from a ``.env``
    file located alongside this package (project root).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///data/job_bot.db",
        description="SQLAlchemy-compatible database URL.",
    )

    # ── AI Configuration ─────────────────────────────────────────────────
    ai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for the OpenAI-compatible API.",
    )
    ai_api_key: str = Field(
        default="sk-...",
        description="API key for the AI provider.",
    )
    ai_model: str = Field(
        default="gpt-4o-mini",
        description="Model name to use for AI completions.",
    )

    # ── Telegram ─────────────────────────────────────────────────────────
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token for notifications.",
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram chat ID to send messages to.",
    )

    # ── Gmail ────────────────────────────────────────────────────────────
    gmail_credentials_path: str = Field(
        default="data/gmail_credentials.json",
        description="Path to Gmail OAuth credentials JSON.",
    )

    # ── Scraping ─────────────────────────────────────────────────────────
    scrape_interval_hours: int = Field(
        default=6,
        description="Hours between automatic scraping runs.",
    )
    max_jobs_per_source: int = Field(
        default=200,
        description="Maximum number of jobs to scrape per source per run.",
    )

    # ── Dashboard ────────────────────────────────────────────────────────
    dashboard_host: str = Field(
        default="127.0.0.1",
        description="Host to bind the web dashboard to.",
    )
    dashboard_port: int = Field(
        default=8000,
        description="Port for the web dashboard.",
    )

    # ── Derived Paths ────────────────────────────────────────────────────
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for persistent data files.",
    )
    resumes_dir: Path = Field(
        default=Path("data/resumes"),
        description="Directory for stored resume files.",
    )
    cover_letters_dir: Path = Field(
        default=Path("data/cover_letters"),
        description="Directory for generated cover letters.",
    )

    # ── Helpers ──────────────────────────────────────────────────────────

    def ensure_dirs(self) -> None:
        """Create all required data directories if they don't exist."""
        for directory in (self.data_dir, self.resumes_dir, self.cover_letters_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
