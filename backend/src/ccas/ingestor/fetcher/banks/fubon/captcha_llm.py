"""Optional Claude Vision fallback for FUBON captcha.

This module is only invoked when ``FUBON_CAPTCHA_FALLBACK_LLM=1`` and the
primary EasyOCR path rejected a sample. The ``anthropic`` SDK is imported
lazily inside :func:`solve_with_llm` so importing this module is free —
users who never enable the fallback do not need to install the optional
``fubon-llm`` dependency group.

Response parsing is strict: Claude must reply with exactly 4 digits or the
result is rejected as a ``CaptchaLlmError``. The caller (flow) treats a
rejected LLM attempt the same as a rejected OCR attempt: burn a retry slot
and refetch the captcha.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re

logger = logging.getLogger(__name__)


_MODEL_ID: str = "claude-sonnet-4-6"
_MAX_TOKENS: int = 16
_PROMPT: str = (
    "This is a 4-digit numeric captcha image. Reply with exactly 4 digits, "
    "nothing else."
)
_DIGITS_RE = re.compile(r"^\d{4}$")


class CaptchaLlmError(RuntimeError):
    """Base class for LLM captcha fallback failures."""


class CaptchaLlmUnavailableError(CaptchaLlmError):
    """The LLM fallback cannot run at all.

    Raised for misconfiguration / infrastructure problems that will not be
    fixed by retrying: missing ``anthropic`` SDK, bad API key, Anthropic
    API outage. The flow layer must treat this as fail-loud rather than
    burning a retry slot, otherwise operators silently get
    ``captcha_retry_exhausted`` even though the documented fallback was
    never functional.
    """


class CaptchaLlmRejectedError(CaptchaLlmError):
    """The LLM was reached but the response was not a valid 4-digit answer.

    Retry-able: the flow layer should burn one retry slot and try again.
    """


async def solve_with_llm(jpeg_bytes: bytes, *, api_key: str) -> str:
    """Ask Claude Vision to read a 4-digit captcha.

    Raises:
        CaptchaLlmUnavailableError: SDK missing or API call failed before
            a response was received (auth / network / outage).
        CaptchaLlmRejectedError: API replied but the content does not
            match ``^\\d{4}$``.
    """
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as exc:
        raise CaptchaLlmUnavailableError(
            "anthropic SDK not installed; install with 'pip install ccas[fubon-llm]'"
        ) from exc

    client = anthropic.AsyncAnthropic(api_key=api_key)
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    try:
        response = await client.messages.create(
            model=_MODEL_ID,
            max_tokens=_MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
    except asyncio.CancelledError:
        # Never swallow cancellation — must propagate so callers can
        # tear down the async task tree cleanly.
        raise
    except Exception as exc:  # noqa: BLE001 -- SDK raises domain-specific types
        raise CaptchaLlmUnavailableError(
            f"anthropic API error: {exc}"
        ) from exc

    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = str(getattr(block, "text", "")).strip()
            break

    if not _DIGITS_RE.match(text):
        raise CaptchaLlmRejectedError(f"LLM response not 4 digits: {text!r}")
    return text
