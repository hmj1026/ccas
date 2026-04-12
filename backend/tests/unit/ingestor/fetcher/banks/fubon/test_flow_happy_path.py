"""FUBON flow — happy path (credentials set, captcha OK first try)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha, flow

MAIN_INFO = {
    "billPeriod": "11504",
    "batchPeriod": "20260410",
    "uniqueIdentifier": "uid123",
    "twYearMonth": "11504",
}


def _email_html(serial: str = "1e79254d8b8c42f1a5c15aa54a0c6616") -> str:
    return (
        f'<html><a href="https://fbmbill.taipeifubon.com.tw/{serial}">帳單</a></html>'
    )


@pytest.mark.asyncio
async def test_download_completes_on_first_captcha() -> None:
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.open_spa = AsyncMock()
    fake_client.get_captcha = AsyncMock(return_value=("srv_tok", b"\xff\xd8\xffjpeg"))
    fake_client.do_login = AsyncMock()
    fake_client.get_main_info = AsyncMock(return_value=MAIN_INFO)
    fake_client.get_bill_pdf = AsyncMock(return_value=b"%PDF-1.4\nfake")

    with (
        patch.object(flow, "FubonClient", return_value=fake_client),
        patch.object(
            captcha,
            "solve",
            return_value=captcha.CaptchaResult(text="4707", confidence=0.98),
        ),
    ):
        result = await flow.download(
            email_html=_email_html(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=7,
            llm_fallback=False,
            llm_api_key=None,
        )
    assert result.startswith(b"%PDF")
    fake_client.open_spa.assert_awaited_once()
    fake_client.get_captcha.assert_awaited_once()
    fake_client.do_login.assert_awaited_once()
    login_kwargs = fake_client.do_login.await_args.kwargs
    assert login_kwargs["captcha_answer"] == "4707"
    assert login_kwargs["server_token"] == "srv_tok"
    assert login_kwargs["serial_key"] == "1e79254d8b8c42f1a5c15aa54a0c6616"
    fake_client.get_main_info.assert_awaited_once()
    fake_client.get_bill_pdf.assert_awaited_once_with(
        bill_period="11504",
        batch_period="20260410",
        uid="uid123",
        tw_year_month="11504",
    )
