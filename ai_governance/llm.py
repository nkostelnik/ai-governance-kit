"""The one place the kit talks to the Claude API.

Everything else in the kit is plain Python that can be tested without a
network connection. Callers pass a Pydantic model as `output_format`; the SDK
constrains Claude's response to that schema and validates it.

The API key is read from the environment (ANTHROPIC_API_KEY, or an
`ant auth login` profile). It is never stored in this repository.
"""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = "claude-sonnet-5-5"

T = TypeVar("T", bound=BaseModel)


class LLMResult(BaseModel):
    """What came back, or why nothing usable did."""

    parsed: object | None          # an instance of the requested output_format, or None
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0


def parse(system: str, user: str, output_format: type[T], effort: str = "medium") -> LLMResult:
    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=output_format,
        output_config={"effort": effort},
        cache_control={"type": "ephemeral"},   # the system prompt is identical across calls
        # If a safety classifier declines, retry server-side on Anthropic's
        # recommended fallback model instead of failing outright.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    usable = response.stop_reason not in ("refusal", "max_tokens")
    return LLMResult(
        parsed=response.parsed_output if usable else None,
        stop_reason=response.stop_reason,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
