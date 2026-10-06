import json
import logging
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """The AI service cannot be used right now. The message is safe to show users."""


def is_configured() -> bool:
    return bool((settings.openai_api_key or "").strip())


def complete_json(system: str, user: str, max_tokens: int = 1200) -> dict[str, Any]:
    if not is_configured():
        raise LLMUnavailable("AI narration is off because no OpenAI API key is configured.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMUnavailable("The 'openai' package is not installed.") from exc

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=max_tokens,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("The AI returned an unreadable answer.") from exc
    except Exception as exc:  # network, auth, rate limit, bad model name...
        logger.warning("OpenAI call failed: %s", type(exc).__name__)
        raise LLMUnavailable("The AI service is not available right now.") from exc

    if not isinstance(data, dict):
        raise LLMUnavailable("The AI returned an unexpected answer.")
    return data