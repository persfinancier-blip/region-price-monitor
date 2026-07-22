"""Application configuration loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for region-price-monitor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/region_price_monitor"
    schedule_cron: str = "0 */6 * * *"
    max_concurrency: int = 5
    retry_limit: int = 3

    proxy_provider: str = "static"
    proxy_url: str | None = None

    home_region: str = "msk"
    wb_card_url: str = "https://card.wb.ru/cards/v2/detail"
    http_timeout_s: int = 30


def get_settings() -> Settings:
    """Return a fresh Settings instance (reads current environment)."""
    return Settings()
