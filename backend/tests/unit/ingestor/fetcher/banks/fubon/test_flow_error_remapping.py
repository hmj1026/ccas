"""FUBON flow — error remapping at the flow boundary.

Covers the ``except FetchError: raise`` and ``except FubonFlowError`` branches
in ``flow.download()``, plus credential-error slug mapping in
``_login_with_captcha_retry``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha, flow
from ccas.ingestor.fetcher.banks.fubon.errors import (
    FubonLoginError,
    FubonRedirectError,
    FubonSessionError,
)
from ccas.ingestor.fetcher.base import FetchError

MAIN_INFO = {
    "billPeriod": "11504",
    "batchPeriod": "20260410",
    "uniqueIdentifier": "uid",
    "twYearMonth": "11504",
}


def _email() -> str:
    return '<html><a href="https://fbmbill.taipeifubon.com.tw/serial123">x</a></html>'


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
async def test_redirect_error_remapped_to_fetch_error() -> None:
    c = _fake_client()
    c.open_spa = AsyncMock(
        side_effect=FubonRedirectError("redirect escapes allowlist: host='evil.com'")
    )
    with patch.object(flow, "FubonClient", return_value=c):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
            )
    assert "flow_error:" in str(exc_info.value)


@pytest.mark.asyncio
async def test_session_error_remapped_to_fetch_error() -> None:
    c = _fake_client()
    c.get_bill_pdf = AsyncMock(
        side_effect=FubonSessionError("PDFReportProc http 401")
    )
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
            )
    assert "flow_error:" in str(exc_info.value)
    assert "PDFReportProc" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_error_passes_through_unchanged() -> None:
    """FetchError raised inside the try block must pass through, not be
    double-wrapped in another FetchError."""
    c = _fake_client()
    original = FetchError("FUBON", "no_download_link: test")
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(flow, "_extract_serial_key", side_effect=original),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
            )
    assert exc_info.value is original
    assert "flow_error:" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_birthday_wrong_maps_to_credentials_wrong() -> None:
    c = _fake_client()
    c.do_login = AsyncMock(
        side_effect=FubonLoginError(
            "birthday_wrong", raw_code=None, message="出生日期不符"
        )
    )
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
            )
    assert "credentials_wrong" in str(exc_info.value)
    assert c.do_login.await_count == 1


@pytest.mark.asyncio
async def test_unknown_login_error_maps_to_credentials_wrong() -> None:
    c = _fake_client()
    c.do_login = AsyncMock(
        side_effect=FubonLoginError("unknown", raw_code=None, message="系統維護中")
    )
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
    ):
        with pytest.raises(FetchError) as exc_info:
            await flow.download(
                email_html=_email(),
                id_number="A123456789",
                birthday="0850101",
            )
    assert "credentials_wrong" in str(exc_info.value)
    assert c.do_login.await_count == 1
