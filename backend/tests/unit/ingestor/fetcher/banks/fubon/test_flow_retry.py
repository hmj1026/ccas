"""FUBON flow — retry loop on rejected captcha / captcha_wrong from doLogin."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha, flow
from ccas.ingestor.fetcher.banks.fubon.errors import FubonLoginError
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
async def test_download_retries_on_rejected_captcha() -> None:
    c = _fake_client()
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", side_effect=[None, None, None, good]),
    ):
        result = await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=7,
        )
    assert result.startswith(b"%PDF")
    assert c.get_captcha.await_count == 4
    assert c.do_login.await_count == 1


@pytest.mark.asyncio
async def test_download_raises_retry_exhausted() -> None:
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
            )
    assert "captcha_retry_exhausted" in str(exc_info.value)
    assert c.get_captcha.await_count == 3
    c.do_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_retries_on_do_login_captcha_wrong() -> None:
    c = _fake_client()
    c.do_login = AsyncMock(
        side_effect=[
            FubonLoginError("captcha_wrong", raw_code=9999),
            FubonLoginError("captcha_wrong", raw_code=9999),
            None,
        ]
    )
    good = captcha.CaptchaResult(text="4707", confidence=0.98)
    with (
        patch.object(flow, "FubonClient", return_value=c),
        patch.object(captcha, "solve", return_value=good),
    ):
        result = await flow.download(
            email_html=_email(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=7,
        )
    assert result.startswith(b"%PDF")
    assert c.get_captcha.await_count == 3
    assert c.do_login.await_count == 3


@pytest.mark.asyncio
async def test_download_no_retry_on_record_not_found() -> None:
    """Stale / already-fetched serial_key must surface as ``record_not_found``
    (soft skip) rather than being rewritten to ``credentials_wrong`` — which
    would mislead operators into checking ID/birthday."""
    c = _fake_client()
    c.do_login = AsyncMock(
        side_effect=FubonLoginError(
            "record_not_found", raw_code=None, message="登入失敗, 查無資料"
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
                max_retries=7,
            )
    assert "record_not_found" in str(exc_info.value)
    assert "credentials_wrong" not in str(exc_info.value)
    assert c.get_captcha.await_count == 1
    assert c.do_login.await_count == 1


@pytest.mark.asyncio
async def test_download_no_retry_on_id_wrong() -> None:
    c = _fake_client()
    c.do_login = AsyncMock(side_effect=FubonLoginError("id_wrong", raw_code=1001))
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
                max_retries=7,
            )
    assert "credentials_wrong" in str(exc_info.value)
    assert c.get_captcha.await_count == 1
    assert c.do_login.await_count == 1
