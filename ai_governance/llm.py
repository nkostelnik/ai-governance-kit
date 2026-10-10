"""The one place the kit talks to the Claude API.

Everything else in the kit is plain Python that can be tested without a
network connection. Callers pass a Pydantic model as `output_format`; the SDK
constrains Claude's response to that schema and validates it.

The API key is read from the environment (ANTHROPIC_API_KEY, or an
`ant auth login` profile), or from a local .env file that git ignores.
It is never stored in this repository.
"""

import os
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

MODEL = "claude-sonnet-5-5"

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Read KEY=VALUE lines from .env into the environment, without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        value = value.strip().strip('"').strip("'")
        # Skip blank values: an empty ANTHROPIC_API_KEY would still take
        # precedence over an `ant auth login` profile and fail authentication.
        if sep and key and value and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value)

T = TypeVar("T", bound=BaseModel)


class LLMResult(BaseModel):
    """What came back, or why nothing usable did."""

    parsed: object | None          # an instance of the requested output_format, or None
    stop_reason: str | None
    input_tokens: int = 0          # uncached input
    cache_write_tokens: int = 0    # billed at 1.25x input
    cache_read_tokens: int = 0     # billed at 0.1x input
    output_tokens: int = 0

    def cost_usd(self, input_per_m: float = 2.0, output_per_m: float = 10.0) -> float:
        """Approximate cost at Sonnet 5.5 list prices ($2 / $10 per million tokens)."""
        billed_input = self.input_tokens + 1.25 * self.cache_write_tokens + 0.1 * self.cache_read_tokens
        return (billed_input * input_per_m + self.output_tokens * output_per_m) / 1e6


def parse(system: str, user: str, output_format: type[T], effort: str = "medium",
          cached_context: str | None = None) -> LLMResult:
    """One structured-output call. `cached_context` (e.g. a vendor's documents)
    goes before `user` and is cached, so repeated calls over the same
    documents with different questions read it from cache."""
    load_env_file()
    client = anthropic.Anthropic()
    content = [{"type": "text", "text": user}]
    if cached_context:
        content.insert(0, {"type": "text", "text": cached_context, "cache_control": {"type": "ephemeral"}})
    try:
        response = _call(client, system, content, output_format, effort)
    except ValidationError:   # the response did not fit the schema: fail closed
        return LLMResult(parsed=None, stop_reason="invalid_output")
    usable = response.stop_reason not in ("refusal", "max_tokens")
    return LLMResult(
        parsed=response.parsed_output if usable else None,
        stop_reason=response.stop_reason,
        input_tokens=response.usage.input_tokens,
        cache_write_tokens=response.usage.cache_creation_input_tokens or 0,
        cache_read_tokens=response.usage.cache_read_input_tokens or 0,
        output_tokens=response.usage.output_tokens,
    )


def _call(client, system, content, output_format, effort):
    return client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        # Cache the system prompt (identical across calls). The marker goes on
        # the system block, not the whole request: the user message differs
        # every call, so caching through it would never produce a cache hit.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        output_format=output_format,
        output_config={"effort": effort},
        # If a safety classifier declines, retry server-side on Anthropic's
        # recommended fallback model instead of failing outright.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
