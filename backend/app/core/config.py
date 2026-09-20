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
    auth_enabled: bool = True
    auth_session_cookie_name: str = "datapilot_session"
    auth_session_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, ge=300, le=30 * 24 * 60 * 60)
    auth_cookie_secure: bool = False
    auth_rate_limit_requests: int = Field(default=120, ge=1, le=100_000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_login_rate_limit_requests: int = Field(default=10, ge=1, le=10_000)
    sandbox_image: str = "datapilot/sandbox:dev"
    sandbox_timeout_seconds: int = 10
    sandbox_memory_limit: str = "512m"
    sandbox_pids_limit: int = 64
    sandbox_cpu_limit: float = 1.0
    sandbox_output_limit_bytes: int = 8192
    sandbox_max_code_lines: int = 300
    sandbox_max_code_chars: int = 80_000
    sandbox_max_input_bytes: int = 48_000
    sandbox_runner_url: str = "http://localhost:18100"
    sandbox_runner_token: SecretStr | None = None
    sandbox_runner_timeout_seconds: float = 12
    sandbox_dataset_volume: str = "datapilot_dataset_data"
    sandbox_artifact_work_volume: str = "datapilot_artifact_work_data"
    sandbox_artifact_work_root: Path = Path("data/artifact-work")
    sandbox_artifact_max_files: int = 20
    sandbox_artifact_max_bytes: int = 10 * 1024 * 1024
    artifact_storage_dir: Path = Path("data/artifacts")
    postgres_query_timeout_seconds: int = 10
    postgres_max_rows: int = 1000
    dataset_restore_on_startup: bool = False
    chat_runtime_mode: Literal["preview", "agent", "disabled"] = "disabled"
    chat_history_limit: int = 20
    chat_history_char_budget: int = 12_000
    agent_max_steps: int = 10
    agent_max_total_tokens: int = 49_152
    agent_max_tool_calls_per_step: int = 3
    agent_max_tool_budget_retries: int = 1
    agent_max_parallel_tools: int = 3
    agent_context_char_budget: int = 24_000
    agent_keep_recent_tool_results: int = 6
    agent_parallel_tools: bool = True
    mcp_enabled: bool = False
    mcp_server_command: str | None = None
    mcp_server_args: list[str] = Field(default_factory=lambda: ["-m", "app.mcp.server"])
    mcp_startup_timeout_seconds: float = 10
    mcp_connect_attempts: int = Field(default=3, ge=1, le=10)
    mcp_retry_base_delay_seconds: float = Field(default=0.5, ge=0, le=30)
    mcp_retry_max_delay_seconds: float = Field(default=5, ge=0, le=60)
    mcp_healthcheck_interval_seconds: float = Field(default=15, ge=1, le=600)
    mcp_tool_refresh_interval_seconds: float = Field(default=300, ge=0, le=3600)
    mcp_call_retry_attempts: int = Field(default=1, ge=0, le=3)
    llm_provider_name: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_default_model: str = "gpt-4o-mini"
    llm_task_models: dict[str, str] = Field(default_factory=dict)
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 2
    llm_retry_base_delay_seconds: float = 0.5
    llm_include_usage_in_stream: bool = True
    llm_input_price_per_million: float = 0
    llm_output_price_per_million: float = 0
    dataset_upload_dir: Path = Path("data/uploads")
    dataset_max_upload_bytes: int = 20 * 1024 * 1024
    dataset_max_rows: int = 500_000
    dataset_max_columns: int = 500

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
