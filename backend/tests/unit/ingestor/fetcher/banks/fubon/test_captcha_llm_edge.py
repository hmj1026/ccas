"""Edge-case tests for captcha_llm.solve_with_llm — response parsing, errors."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha_llm


def _fake_anthropic(response_content: list) -> MagicMock:
    fake = MagicMock()
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = response_content
    fake_client.messages.create = AsyncMock(return_value=fake_response)
    fake.AsyncAnthropic.return_value = fake_client
    return fake


@pytest.mark.asyncio
async def test_empty_content_list_rejected() -> None:
    fake = _fake_anthropic(response_content=[])
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(captcha_llm.CaptchaLlmRejectedError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


@pytest.mark.asyncio
async def test_whitespace_around_digits_accepted() -> None:
    fake = _fake_anthropic([MagicMock(type="text", text="  4707  ")])
    with patch.dict(sys.modules, {"anthropic": fake}):
        result = await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")
    assert result == "4707"


@pytest.mark.asyncio
async def test_5_digit_rejected() -> None:
    fake = _fake_anthropic([MagicMock(type="text", text="47071")])
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(captcha_llm.CaptchaLlmRejectedError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


@pytest.mark.asyncio
async def test_3_digit_rejected() -> None:
    fake = _fake_anthropic([MagicMock(type="text", text="470")])
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(captcha_llm.CaptchaLlmRejectedError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


@pytest.mark.asyncio
async def test_cancelled_error_propagates() -> None:
    fake = MagicMock()
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(side_effect=asyncio.CancelledError())
    fake.AsyncAnthropic.return_value = fake_client
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(asyncio.CancelledError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


@pytest.mark.asyncio
async def test_no_text_block_rejected() -> None:
    """Response with only image blocks → rejected (empty text)."""
    fake = _fake_anthropic([MagicMock(type="image", text=None)])
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(captcha_llm.CaptchaLlmRejectedError):
            await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")


@pytest.mark.asyncio
async def test_multiple_content_blocks_uses_first_text() -> None:
    blocks = [
        MagicMock(type="image", text=None),
        MagicMock(type="text", text="4707"),
        MagicMock(type="text", text="9999"),
    ]
    fake = _fake_anthropic(blocks)
    with patch.dict(sys.modules, {"anthropic": fake}):
        result = await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")
    assert result == "4707"


@pytest.mark.asyncio
async def test_correct_model_and_max_tokens() -> None:
    fake = _fake_anthropic([MagicMock(type="text", text="1234")])
    with patch.dict(sys.modules, {"anthropic": fake}):
        await captcha_llm.solve_with_llm(b"\xff\xd8\xff", api_key="sk-test")
    create_call = fake.AsyncAnthropic.return_value.messages.create
    kwargs = create_call.await_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 16
