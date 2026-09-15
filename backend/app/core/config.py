from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataPilot API"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = (
        "postgresql+asyncpg://datapilot:datapilot_dev_password@localhost:25432/datapilot"
    )
    redis_url: str = "redis://localhost:26379/0"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:18080",
        ]
    )
    sandbox_image: str = "datapilot/sandbox:dev"
    sandbox_timeout_seconds: int = 10
    sandbox_memory_limit: str = "512m"
    sandbox_pids_limit: int = 64
    sandbox_cpu_limit: float = 1.0
    sandbox_output_limit_bytes: int = 8192
    sandbox_max_code_lines: int = 300
    sandbox_max_code_chars: int = 80_000
    sandbox_max_input_bytes: int = 48_000
    postgres_query_timeout_seconds: int = 10
    postgres_max_rows: int = 1000
    auto_create_schema: bool = False
    chat_runtime_mode: Literal["preview", "disabled"] = "disabled"
    chat_history_limit: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
