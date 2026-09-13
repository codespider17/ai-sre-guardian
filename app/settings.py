from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_SRE_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str
    ingest_token: str
    capacity_lab_token: str
    resilience_lab_token: str
    service_name: str = "ai-sre-guardian"
    version: str = "0.1.0"

    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_api_key: SecretStr | None = None
    deepseek_timeout_seconds: float = 30.0
    deepseek_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
