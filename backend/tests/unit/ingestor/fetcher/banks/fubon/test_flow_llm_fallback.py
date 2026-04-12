"""FUBON flow — LLM fallback branch."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha, captcha_llm, flow

MAIN_INFO = {
    "billPeriod": "11504",
    "batchPeriod": "20260410",
    "uniqueIdentifier": "uid",
    "twYearMonth": "11504",
}


def _email() -> str:
    return '<html><a href="https://fbmbill.taipeifubon.com.tw/serial">x</a></html>'


def _fake_client() -> MagicMock:
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=None)
    c.open_spa = AsyncMock()
    c.get_captcha = AsyncMock(return_value=("srv", b"\xff\xd8\xffj"))
    c.do_login = AsyncMock()
    c.get_main_info = AsyncMock(return_value=MAIN_INFO)
    c.get_bill_pdf = AsyncMock(return_value=b"%PDF-1.4\n")
    return c


@pytest.mark.asyncio
async def test_llm_fallback_called_when_ocr_rejects() -> None:
    c = _fake_client()
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=None),
        patch.object(
            captcha_llm, "solve_with_llm", AsyncMock(return_value="9999")
        ) as mock_llm,
    ):
        result = await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=7,
            llm_fallback=True,
            llm_api_key="sk-test",
        )
    assert result.startswith(b"%PDF")
    mock_llm.assert_awaited_once()
    assert c.do_login.await_count == 1
    login_kwargs = c.do_login.await_args.kwargs
    assert login_kwargs["captcha_answer"] == "9999"


@pytest.mark.asyncio
async def test_llm_fallback_not_called_when_disabled() -> None:
    c = _fake_client()
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
        patch.object(captcha_llm, "solve_with_llm", AsyncMock()) as mock_llm,
    ):
        await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            llm_fallback=False,
        )
    mock_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_fallback_enabled_without_api_key_fails_loud() -> None:
    """Misconfiguration: ``llm_fallback=True`` but no key must surface a
    distinct ``llm_fallback_unavailable`` FetchError instead of silently
    downgrading to OCR-only and later reporting ``captcha_retry_exhausted``.
    """
    from ccas.ingestor.fetcher.base import FetchError

    c = _fake_client()
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=None),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
                max_retries=3,
                llm_fallback=True,
                llm_api_key=None,
            )
    assert "llm_fallback_unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_fallback_sdk_missing_fails_loud() -> None:
    """If ``CaptchaLlmUnavailable`` is raised (SDK missing / auth error),
    flow must re-raise as ``llm_fallback_unavailable`` FetchError instead of
    burning retry slots and collapsing to ``captcha_retry_exhausted``.
    """
    from ccas.ingestor.fetcher.base import FetchError

    c = _fake_client()
    unavailable = captcha_llm.CaptchaLlmUnavailableError("anthropic SDK not installed")
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=None),
        patch.object(
            captcha_llm,
            "solve_with_llm",
            AsyncMock(side_effect=unavailable),
        ),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
                max_retries=5,
                llm_fallback=True,
                llm_api_key="sk-test",
            )
    assert "llm_fallback_unavailable" in str(exc_info.value)
    assert "captcha_retry_exhausted" not in str(exc_info.value)
    # Must not silently burn all retries before failing.
    assert c.get_captcha.await_count == 1


@pytest.mark.asyncio
async def test_llm_fallback_rejected_response_still_retries() -> None:
    """``CaptchaLlmRejected`` (bad response format) is still a burn-the-slot
    case — distinct from ``CaptchaLlmUnavailable``, the flow must ``continue``
    and keep trying rather than fail-loud."""
    c = _fake_client()
    rejected = captcha_llm.CaptchaLlmRejectedError("LLM response not 4 digits: 'x'")
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=None),
        patch.object(
            captcha_llm,
            "solve_with_llm",
            AsyncMock(side_effect=[rejected, rejected, "4707"]),
        ),
    ):
        result = await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=5,
            llm_fallback=True,
            llm_api_key="sk-test",
        )
    assert result.startswith(b"%PDF")
    assert c.do_login.await_count == 1


@pytest.mark.asyncio
async def test_anthropic_not_imported_when_fallback_disabled() -> None:
    """Full flow with llm_fallback=False must not pull anthropic into sys.modules."""
    sys.modules.pop("anthropic", None)
    c = _fake_client()
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
    ):
        await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            llm_fallback=False,
        )
    assert "anthropic" not in sys.modules
