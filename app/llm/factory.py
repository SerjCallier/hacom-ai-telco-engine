from __future__ import annotations

from functools import lru_cache

from app.config import LlmSettings, get_llm_settings
from app.llm.base import LLMNotConfigured, LLMProvider
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAiCompatibleProvider


def build_provider(settings: LlmSettings) -> LLMProvider:
    if settings.provider == "mock":
        return MockProvider()

    if settings.provider == "openai":
        if not settings.api_key:
            raise LLMNotConfigured(
                "LLM_PROVIDER=openai requires LLM_API_KEY. Leave LLM_PROVIDER=mock to run "
                "without credentials."
            )
        return OpenAiCompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            temperature=settings.temperature,
        )

    raise LLMNotConfigured(f"Unsupported LLM_PROVIDER: {settings.provider!r}")


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_llm_settings())
