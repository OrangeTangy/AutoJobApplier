from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.llm.anthropic_client import AnthropicProvider
from app.services.llm.base import LLMProvider, LLMResponse
from app.services.llm.mock_client import MockProvider

__all__ = ["LLMProvider", "LLMResponse", "get_llm_provider"]


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicProvider()
    return MockProvider()
