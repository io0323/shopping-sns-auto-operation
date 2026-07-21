from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rakuten_app_id: str = ""
    rakuten_affiliate_id: str = ""
    anthropic_api_key: str = ""
    monthly_llm_budget_jpy: int = 3000
    database_url: str = "sqlite:///./data.db"
    model_generator: str = "claude-sonnet-5"
    model_evaluator: str = "claude-haiku-4-5"
    usd_jpy_rate: float = 150.0
    slack_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
