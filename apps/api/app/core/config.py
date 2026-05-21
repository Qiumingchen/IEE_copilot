from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "iee_minio"
    minio_secret_key: str = "iee_minio_password"
    minio_bucket: str = "iee-artifacts"
    minio_secure: bool = False
    api_secret_key: str = "dev-secret"
    access_token_expire_minutes: int = 1440
    skip_db_healthcheck: bool = False
    allow_science_fallbacks: bool = True
    use_real_science_providers: bool = False
    homolog_provider_fetch_size: int = 25
    mafft_bin: str | None = None
    rosetta_ddg_bin: str | None = None
    rosetta_ddg_command: str | None = None
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
