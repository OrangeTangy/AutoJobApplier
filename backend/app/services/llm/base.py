from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str


class LLMProvider(ABC):
    """Abstract LLM interface — swap providers without changing callers."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    @abstractmethod
    async def complete_structured(
        self,
        prompt: str,
        output_schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> T: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
