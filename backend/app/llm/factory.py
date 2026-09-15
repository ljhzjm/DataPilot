from app.core.config import Settings
from app.llm.cost import UsageTrackingProvider
from app.llm.openai_compat import OpenAICompatibleProvider
from app.llm.router import ModelRouter


def build_model_router(settings: Settings) -> ModelRouter | None:
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
        return None

    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        default_model=settings.llm_default_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_base_delay_seconds=settings.llm_retry_base_delay_seconds,
        include_usage_in_stream=settings.llm_include_usage_in_stream,
    )
    tracked_provider = UsageTrackingProvider(
        provider,
        provider_name=settings.llm_provider_name,
    )
    return ModelRouter(
        provider=tracked_provider,
        default_model=settings.llm_default_model,
        task_models=settings.llm_task_models,
    )
