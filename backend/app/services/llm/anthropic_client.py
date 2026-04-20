from __future__ import annotations

import json
import re
from typing import TypeVar

import anthropic
import structlog
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.llm.base import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

_SYSTEM_PREAMBLE = """You are a job application assistant. You help users tailor their
resumes and prepare application answers. You NEVER fabricate qualifications, work
history, dates, sponsorship status, clearance, GPA, or skills. Every answer you
generate MUST be grounded in the user profile data provided to you.

When you generate structured output, respond with valid JSON only — no markdown fences,
no explanation text outside the JSON object."""


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens

    @property
    def model_name(self) -> str:
        return self._model

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        full_system = f"{_SYSTEM_PREAMBLE}\n\n{system}".strip()
        logger.debug("llm_request", model=self._model, prompt_len=len(prompt))

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=full_system,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text if message.content else ""
        response = LLMResponse(
            content=content,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            model=self._model,
            stop_reason=message.stop_reason or "end_turn",
        )
        logger.debug(
            "llm_response",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
        )
        return response

    async def complete_structured(
        self,
        prompt: str,
        output_schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> T:
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        augmented_system = (
            f"{system}\n\nRespond with a single JSON object matching this schema:\n{schema_json}"
        )
        resp = await self.complete(
            prompt, system=augmented_system, max_tokens=max_tokens, temperature=temperature
        )
        raw = resp.content.strip()
        # Strip markdown fences if model included them despite instructions
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
            return output_schema.model_validate(data)
        except Exception as exc:
            logger.error("llm_parse_error", raw=raw[:500], error=str(exc))
            raise ValueError(f"LLM response could not be parsed as {output_schema.__name__}") from exc
