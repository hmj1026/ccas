"""Deterministic end-to-end coverage for the FUBON CAPTCHA download flow.

The upstream SPA is replaced at the HTTP boundary with ``respx`` routes, but
the real serial-key extraction, HTTP client, CAPTCHA OCR, retry loop, login
state and PDF download path are exercised together.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import flow
from ccas.ingestor.fetcher.base import FetchError

_HOST = "https://fbmbill.taipeifubon.com.tw"
_SERIAL = "1e79254d8b8c42f1a5c15aa54a0c6616"
_ENTRY_URL = f"{_HOST}/{_SERIAL}"
_SPA_URL = f"{_HOST}/client/pdf/{_SERIAL}"
_CAPTCHA_URL = f"{_HOST}/checkImgs/captcha.jpg"
_LOGIN_URL = f"{_HOST}/doLogin"
_PDF_URL = f"{_HOST}/PDFReportProc"
_CAPTCHA_IMAGE = (
    Path(__file__).parents[2] / "fixtures" / "fubon" / "captcha_samples" / "6372.jpg"
).read_bytes()
_CAPTCHA_B64 = base64.b64encode(_CAPTCHA_IMAGE).decode("ascii")
_MAIN_INFO = {
    "billPeriod": "11504",
    "batchPeriod": "20260410",
    "uniqueIdentifier": "uid123",
    "twYearMonth": "11504",
}
_SUCCESS_BODY = {
    "errorMsg": None,
    "jwt": "jwt.test.token",
    **_MAIN_INFO,
}
_CAPTCHA_ERROR_BODY = {
    "errorMsg": "登入失敗, 請確認圖形驗證碼是否輸入正確",
    "jwt": None,
}


def _email_html() -> str:
    return f'<html><a href="{_ENTRY_URL}">查看帳單</a></html>'


def _captcha_response(token: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=f"{token},{_CAPTCHA_B64}",
    )


def _register_spa_routes(mock: respx.MockRouter) -> None:
    mock.get(_ENTRY_URL).mock(
        return_value=httpx.Response(
            302,
            headers={"location": _SPA_URL, "set-cookie": "JSESSIONID=e2e"},
        )
    )
    mock.get(_SPA_URL).mock(return_value=httpx.Response(200, text="<html>SPA</html>"))


@pytest.mark.asyncio
async def test_fubon_download_runs_real_flow_with_fixture_captcha() -> None:
    """A valid fixture CAPTCHA reaches the real PDF download boundary."""
    async with respx.mock() as mock:
        _register_spa_routes(mock)
        captcha_route = mock.get(_CAPTCHA_URL).mock(
            return_value=_captcha_response("token-1")
        )
        login_route = mock.post(_LOGIN_URL).mock(
            return_value=httpx.Response(200, json=_SUCCESS_BODY)
        )
        pdf_route = mock.get(_PDF_URL).mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7\nfixture")
        )

        result = await flow.download(
            email_html=_email_html(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=2,
        )

    assert result.startswith(b"%PDF")
    assert len(captcha_route.calls) == 1
    assert len(login_route.calls) == 1
    assert len(pdf_route.calls) == 1
    login_payload = json.loads(login_route.calls[0].request.content)
    assert login_payload == {
        "id": "A123456789",
        "birthday": "0850101",
        "serialKey": _SERIAL,
        "captchaCode": "token-1,6372",
    }


@pytest.mark.asyncio
async def test_fubon_download_refetches_captcha_after_server_rejection() -> None:
    """A server-side CAPTCHA rejection refetches a fresh CAPTCHA and retries."""
    async with respx.mock() as mock:
        _register_spa_routes(mock)
        captcha_route = mock.get(_CAPTCHA_URL).mock(
            side_effect=[_captcha_response("token-1"), _captcha_response("token-2")]
        )
        login_route = mock.post(_LOGIN_URL).mock(
            side_effect=[
                httpx.Response(200, json=_CAPTCHA_ERROR_BODY),
                httpx.Response(200, json=_SUCCESS_BODY),
            ]
        )
        mock.get(_PDF_URL).mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7\nretry")
        )

        result = await flow.download(
            email_html=_email_html(),
            id_number="A123456789",
            birthday="0850101",
            max_retries=2,
        )

    assert result.startswith(b"%PDF")
    assert len(captcha_route.calls) == 2
    assert len(login_route.calls) == 2
    first_payload = json.loads(login_route.calls[0].request.content)
    second_payload = json.loads(login_route.calls[1].request.content)
    assert first_payload["captchaCode"] == "token-1,6372"
    assert second_payload["captchaCode"] == "token-2,6372"


@pytest.mark.asyncio
async def test_fubon_download_reports_retry_exhaustion_without_pdf_request() -> None:
    """Repeated server rejection stops at the configured retry limit."""
    async with respx.mock(assert_all_called=False) as mock:
        _register_spa_routes(mock)
        captcha_route = mock.get(_CAPTCHA_URL).mock(
            side_effect=[_captcha_response("token-1"), _captcha_response("token-2")]
        )
        login_route = mock.post(_LOGIN_URL).mock(
            side_effect=[
                httpx.Response(200, json=_CAPTCHA_ERROR_BODY),
                httpx.Response(200, json=_CAPTCHA_ERROR_BODY),
            ]
        )
        pdf_route = mock.get(_PDF_URL)

        with pytest.raises(
            FetchError, match="captcha_retry_exhausted: 2 attempts failed"
        ):
            await flow.download(
                email_html=_email_html(),
                id_number="A123456789",
                birthday="0850101",
                max_retries=2,
            )

    assert len(captcha_route.calls) == 2
    assert len(login_route.calls) == 2
    assert not pdf_route.called
