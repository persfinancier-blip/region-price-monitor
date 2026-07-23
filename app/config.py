"""Application configuration loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for region-price-monitor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/region_price_monitor"
    schedule_cron: str = "0 */6 * * *"
    max_concurrency: int = 5
    retry_limit: int = 3
    queue_claim_batch: int = 10
    retry_backoff_base_s: float = 2.0
    retry_backoff_max_s: float = 60.0
    queue_lock_ttl_s: int = 600

    proxy_provider: str = "static"
    proxy_url: str | None = None
    proxy_map_json: str | None = None

    proxy_health_enabled: bool = True
    proxy_ban_threshold: int = 3
    proxy_health_window_s: int = 900
    proxy_cooldown_s: int = 1800

    wb_min_interval_s: float = 1.0
    ozon_min_interval_s: float = 2.0
    request_jitter_s: float = 0.5

    home_region: str = "msk"
    wb_card_url: str = "https://card.wb.ru/cards/v2/detail"
    http_timeout_s: int = 30

    ozon_api_url: str = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
    ozon_impersonate: str = "chrome"
    cookie_store_dir: str = "data/cookies"
    ozon_cookie_ttl_hours: int = 12

    log_level: str = "INFO"
    log_format: str = "json"

    success_rate_threshold: float = 0.9
    alert_min_measures: int = 1
    alerter: str = "log"
    alert_webhook_url: str | None = None


def get_settings() -> Settings:
    """Return a fresh Settings instance (reads current environment)."""
    return Settings()
