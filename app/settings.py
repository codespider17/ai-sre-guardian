from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_SRE_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str
    service_name: str = "ai-sre-guardian"
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
