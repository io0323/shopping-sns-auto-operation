from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    model_learning: str = "claude-sonnet-5"
    usd_jpy_rate: float = 150.0
    slack_webhook_url: str = ""
    # NoDecodeでpydantic-settingsのJSONデコードを止め、下のvalidatorでカンマ区切りを解釈する。
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
