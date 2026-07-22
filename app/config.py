"""Application settings, loaded from environment / .env (ADR-0001)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for region-price-monitor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/region_price_monitor"
    schedule_cron: str = "0 */6 * * *"
    max_concurrency: int = 5
    retry_limit: int = 3

    proxy_provider: str = ""
    proxy_api_key: str = ""


settings = Settings()
