"""Mock LLM provider for tests and local dev without an API key."""
from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from app.services.llm.base import LLMProvider, LLMResponse

T = TypeVar("T", bound=BaseModel)


class MockProvider(LLMProvider):
    """Returns deterministic stub responses — never calls external APIs."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-provider"

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self._call_count += 1
        content = self._responses.get(prompt[:50], "Mock LLM response")
        return LLMResponse(
            content=content,
            input_tokens=len(prompt) // 4,
            output_tokens=len(content) // 4,
            model="mock-provider",
            stop_reason="end_turn",
        )

    async def complete_structured(
        self,
        prompt: str,
        output_schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> T:
        self._call_count += 1
        # Return a minimal valid instance of the schema
        try:
            defaults = _build_defaults(output_schema)
            return output_schema.model_validate(defaults)
        except Exception:
            return output_schema.model_construct()


def _build_defaults(schema: type[BaseModel]) -> dict:
    """Build a minimal dict that satisfies a Pydantic schema."""
    result: dict = {}
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        if annotation is str or annotation == "str":
            result[name] = "mock_value"
        elif annotation is int:
            result[name] = 0
        elif annotation is float:
            result[name] = 0.0
        elif annotation is bool:
            result[name] = False
        elif annotation is list or (hasattr(annotation, "__origin__") and annotation.__origin__ is list):
            result[name] = []
        elif annotation is dict or (hasattr(annotation, "__origin__") and annotation.__origin__ is dict):
            result[name] = {}
        elif field.default is not None:
            result[name] = field.default
    return result
