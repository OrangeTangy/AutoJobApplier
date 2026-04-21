from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.llm.base import LLMProvider, LLMResponse
from app.services.llm.mock_client import MockProvider

__all__ = ["LLMProvider", "LLMResponse", "get_llm_provider"]


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Returns an LLM provider instance.

    Anthropic support is optional — only available if:
    1. `anthropic` package is installed (uncomment in requirements.txt)
    2. ANTHROPIC_API_KEY is set in the environment

    Without those, returns MockProvider which satisfies the interface
    but returns minimal placeholder responses.
    """
    settings = get_settings()
    if settings.anthropic_api_key:
        try:
            from app.services.llm.anthropic_client import AnthropicProvider
            return AnthropicProvider()
        except ImportError:
            pass  # anthropic package not installed — fall through to mock
    return MockProvider()
