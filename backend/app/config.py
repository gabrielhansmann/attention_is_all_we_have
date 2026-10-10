"""Settings and paths shared by the API, the agents and the ingest scripts.

The repository root holds the single `.env` and the gitignored `data/` folder, so everything works
from any working directory. Secrets are read from the environment only and never logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
ENV_FILE = REPO_ROOT / ".env"


def load_env() -> None:
    """Load the repo-root .env (does not override variables already set in the environment)."""
    load_dotenv(ENV_FILE)


@dataclass(frozen=True)
class Settings:
    db_url: str | None
    openai_api_key_set: bool
    openai_chat_model: str
    embed_model: str
    cors_origins: list[str]
    session_hours: int = 12
    production: bool = False


def get_settings() -> Settings:
    load_env()
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        db_url=os.environ.get("SUPABASE_DB_URL"),
        openai_api_key_set=bool(os.environ.get("OPENAI_API_KEY")),
        openai_chat_model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        embed_model="text-embedding-3-small",
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        session_hours=max(1, int(os.environ.get("AUTH_SESSION_HOURS", "12"))),
        production=os.environ.get("APP_ENV", "").lower() == "production",
    )
