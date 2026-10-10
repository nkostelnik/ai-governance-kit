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
from pydantic import BaseModel

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
    input_tokens: int = 0
    output_tokens: int = 0


def parse(system: str, user: str, output_format: type[T], effort: str = "medium") -> LLMResult:
    load_env_file()
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
