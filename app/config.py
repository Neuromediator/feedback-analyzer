"""Application settings loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-6-luna"
    openrouter_reasoning: str = "low"
    analyzer: str = "llm"  # "llm" (chat model) or "jev" (decision model)
    jev_model: str = "typesafe/jev-1.14"
    api_url: str = "http://localhost:8000"
    db_path: str = "feedback.db"


settings = Settings()
