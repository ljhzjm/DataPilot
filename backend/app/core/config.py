from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    chat_runtime_mode: Literal["preview", "agent", "disabled"] = "disabled"
    chat_history_limit: int = 20
    agent_max_steps: int = 8
    agent_max_total_tokens: int = 8192
    agent_parallel_tools: bool = True
    mcp_enabled: bool = False
    mcp_server_command: str | None = None
    mcp_server_args: list[str] = Field(default_factory=lambda: ["-m", "app.mcp.server"])
    mcp_startup_timeout_seconds: float = 10
    llm_provider_name: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_default_model: str = "gpt-4o-mini"
    llm_task_models: dict[str, str] = Field(default_factory=dict)
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 2
    llm_retry_base_delay_seconds: float = 0.5
    llm_include_usage_in_stream: bool = True
    dataset_upload_dir: Path = Path("data/uploads")
    dataset_max_upload_bytes: int = 20 * 1024 * 1024
    dataset_max_rows: int = 500_000
    dataset_max_columns: int = 500

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
