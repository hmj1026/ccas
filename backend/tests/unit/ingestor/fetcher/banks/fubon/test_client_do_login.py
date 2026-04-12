"""Unit tests for FubonClient.do_login — payload schema + JWT + error slugs.

As of 2026-04-11 the FUBON doLogin response shape is::

    {"errorMsg": null | "<chinese-reason>",
     "jwt": null | "<jwt-string>",
     "billPeriod": ..., "twYearMonth": ..., "batchPeriod": ...,
     "uniqueIdentifier": ..., "gk": ..., "ak": ..., "gid": ...,
     "months": [...]}

Success is signalled by ``jwt`` being a non-empty string. Failures are
classified by keyword-matching ``errorMsg`` via
``client._classify_error_msg`` — no numeric ``code`` field exists.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import errors
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient
from ccas.ingestor.fetcher.banks.fubon.errors import FubonSessionError

LOGIN_URL = "https://fbmbill.taipeifubon.com.tw/doLogin"

_SUCCESS_BODY: dict[str, object] = {
    "errorMsg": None,
    "jwt": "xyz.jwt.token",
    "billPeriod": "1150409",
    "twYearMonth": "11504",
    "batchPeriod": "2137",
    "uniqueIdentifier": "aZQvogqGPiKI9MhqzhVRLQ==",
    "gk": "AIzaSy...",
    "ak": "fake-ak",
    "gid": "fake-gid",
    "months": ["11410", "11411", "11412"],
}


@pytest.mark.asyncio
async def test_do_login_posts_correct_payload_and_stores_jwt() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        route = mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json=_SUCCESS_BODY)
        )
        await client.do_login(
            id_number="A123456789",
            birthday="0850101",
            serial_key="1e79",
            captcha_answer="1234",
            server_token="tok",
        )
        assert route.called
        body = json.loads(route.calls.last.request.content)
        assert body == {
            "id": "A123456789",
            "birthday": "0850101",
            "serialKey": "1e79",
            "captchaCode": "tok,1234",
        }
        assert client._jwt == "xyz.jwt.token"


@pytest.mark.asyncio
async def test_do_login_caches_main_info_on_success() -> None:
    """doLogin now returns bill main-info alongside JWT; must be cached."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json=_SUCCESS_BODY)
        )
        await client.do_login(
            id_number="A123456789",
            birthday="0850101",
            serial_key="1e79",
            captcha_answer="1234",
            server_token="tok",
        )
        assert client._main_info == {
            "billPeriod": "1150409",
            "twYearMonth": "11504",
            "batchPeriod": "2137",
            "uniqueIdentifier": "aZQvogqGPiKI9MhqzhVRLQ==",
        }


@pytest.mark.asyncio
async def test_do_login_captcha_wrong_raises_with_slug() -> None:
    """Classification keyword: ``驗證碼`` → captcha_wrong slug."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errorMsg": "登入失敗, 請確認圖形驗證碼是否輸入正確",
                    "jwt": None,
                    "billPeriod": None,
                    "twYearMonth": None,
                    "batchPeriod": None,
                    "uniqueIdentifier": None,
                },
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "captcha_wrong"
        assert client._jwt is None
        assert client._main_info is None


@pytest.mark.asyncio
async def test_do_login_id_wrong_raises_with_slug() -> None:
    """Classification keyword: ``身分證`` → id_wrong slug."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errorMsg": "身分證號不正確", "jwt": None},
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="B123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "id_wrong"


@pytest.mark.asyncio
async def test_do_login_birthday_wrong_raises_with_slug() -> None:
    """Classification keyword: ``出生`` → birthday_wrong slug."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errorMsg": "出生日期不正確", "jwt": None},
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="A123456789",
                birthday="0990101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "birthday_wrong"


@pytest.mark.asyncio
async def test_do_login_record_not_found_maps_to_slug() -> None:
    """Observed in live FUBON mail: expired/already-fetched serial_key replies
    with ``登入失敗, 查無資料`` and must surface as ``record_not_found`` rather
    than collapsing into ``unknown`` (which the flow layer then mis-translates
    into ``credentials_wrong``)."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errorMsg": "登入失敗, 查無資料", "jwt": None},
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "record_not_found"
        assert exc_info.value.raw_message == "登入失敗, 查無資料"


@pytest.mark.asyncio
async def test_do_login_unknown_error_msg_maps_to_unknown() -> None:
    """An errorMsg that matches no keyword → ``unknown`` slug."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errorMsg": "伺服器維護中", "jwt": None},
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "unknown"
        assert exc_info.value.raw_message == "伺服器維護中"


@pytest.mark.asyncio
async def test_do_login_jwt_set_but_main_info_missing_raises_session_error() -> None:
    """jwt truthy but required main_info field missing → FubonSessionError.

    Guards against silently caching ``None`` values that would later be
    ``str()``-ed into ``"None"`` query params inside ``get_bill_pdf``.
    """
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errorMsg": None,
                    "jwt": "xyz.jwt.token",
                    "billPeriod": "1150409",
                    "twYearMonth": "11504",
                    "batchPeriod": None,
                    "uniqueIdentifier": "uid123",
                },
            )
        )
        with pytest.raises(FubonSessionError, match="batchPeriod"):
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert client._jwt is None
        assert client._main_info is None


@pytest.mark.asyncio
async def test_do_login_null_jwt_and_null_error_msg_maps_to_unknown() -> None:
    """Contract break (both jwt and errorMsg null) → unknown slug, not crash."""
    async with FubonClient() as client, respx.mock() as mock:
        mock.post(LOGIN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errorMsg": None, "jwt": None},
            )
        )
        with pytest.raises(errors.FubonLoginError) as exc_info:
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
        assert exc_info.value.code == "unknown"
