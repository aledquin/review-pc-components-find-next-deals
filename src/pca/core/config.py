"""Runtime configuration sourced from env vars + optional .env file."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_NAME = "PCUpgradeAdvisor"
_APP_AUTHOR = "PCUpgradeAdvisor"


class Settings(BaseSettings):
    """Application settings. All env vars are prefixed with ``PCA_``."""

    model_config = SettingsConfigDict(
        env_prefix="PCA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    cache_dir: Path | None = None
    report_dir: Path | None = None

    # Retailer credentials (optional; adapter stays inert if missing).
    bestbuy_api_key: SecretStr | None = None
    amazon_access_key: SecretStr | None = None
    amazon_secret_key: SecretStr | None = None
    amazon_assoc_tag: str | None = None
    amazon_region: str = "us-east-1"
    ebay_client_id: SecretStr | None = None
    ebay_client_secret: SecretStr | None = None
    keepa_api_key: SecretStr | None = None
    newegg_feed_path: Path | None = None

    # Feature flags.
    enable_scrapers: bool = False
    enable_pcpartpicker_compat: bool = False
    # Comma-separated allow-list of adapter names to instantiate.
    # Empty = auto (use every adapter whose credentials are present).
    enable_adapters: str = ""
    allow_plugins: bool = False
    # Network timeout used by the default httpx transport (seconds).
    adapter_http_timeout: float = Field(default=10.0, gt=0.0)

    # Deal-ranker weights (defaults calibrated against KGRs).
    deal_weight_price: float = Field(default=0.5, ge=0.0)
    deal_weight_reputation: float = Field(default=0.2, ge=0.0)
    deal_weight_shipping: float = Field(default=0.1, ge=0.0)
    deal_weight_warranty: float = Field(default=0.1, ge=0.0)
    deal_weight_freshness: float = Field(default=0.1, ge=0.0)

    def resolved_cache_dir(self) -> Path:
        return self.cache_dir or Path(user_cache_dir(_APP_NAME, _APP_AUTHOR))

    def resolved_report_dir(self) -> Path:
        return self.report_dir or (Path(user_data_dir(_APP_NAME, _APP_AUTHOR)) / "reports")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Used by tests to reload env between cases."""
    global _settings
    _settings = None
