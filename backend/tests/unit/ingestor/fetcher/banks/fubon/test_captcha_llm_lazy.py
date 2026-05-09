"""Unit tests for FUBON captcha LLM fallback (Claude Vision).

The LLM fallback is optional and gated by ``FUBON_CAPTCHA_FALLBACK_LLM``. It
must lazy-import ``anthropic`` only when actually invoked so the main code
path does not pay the SDK import cost and users who never enable the feature
do not need to install the ``fubon-llm`` optional dependency.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha_llm


@pytest.mark.asyncio
async def test_solve_with_llm_raises_when_sdk_missing() -> None:
    sys.modules.pop("anthropic", None)
    with patch.dict(sys.modules, {"anthropic": None}):
        with pytest.raises(captcha_llm.CaptchaLlmUnavailableError) as exc_info:
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")
    assert "sdk not installed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_solve_with_llm_api_error_is_unavailable() -> None:
    """Anthropic SDK runtime errors (auth failure, network) must surface as
    ``CaptchaLlmUnavailable`` so the flow layer can fail-loud instead of
    silently burning retry slots."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        side_effect=RuntimeError("401 invalid x-api-key")
    )
    fake_anthropic.AsyncAnthropic.return_value = fake_client

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        with pytest.raises(captcha_llm.CaptchaLlmUnavailableError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-bad")


@pytest.mark.asyncio
async def test_solve_with_llm_parses_response() -> None:
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="4707")]
    fake_client.messages.create = AsyncMock(return_value=fake_response)
    fake_anthropic.AsyncAnthropic.return_value = fake_client

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        result = await captcha_llm.solve_with_llm(
            b"\xff\xd8\xffjpegbytes", api_key="sk-test"
        )

    assert result == "4707"
    fake_anthropic.AsyncAnthropic.assert_called_once_with(api_key="sk-test")
    fake_client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_solve_with_llm_rejects_non_4_digit_response() -> None:
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="not a number")]
    fake_client.messages.create = AsyncMock(return_value=fake_response)
    fake_anthropic.AsyncAnthropic.return_value = fake_client

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        with pytest.raises(captcha_llm.CaptchaLlmRejectedError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


def test_module_does_not_import_anthropic_at_load() -> None:
    """Importing captcha_llm itself must not pull in anthropic."""
    sys.modules.pop("anthropic", None)
    import importlib

    import ccas.ingestor.fetcher.banks.fubon.captcha_llm as mod

    importlib.reload(mod)
    assert "anthropic" not in sys.modules
