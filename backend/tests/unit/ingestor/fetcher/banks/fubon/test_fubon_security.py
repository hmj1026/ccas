"""Security-focused tests for FUBON fetcher — SSRF, scheme filtering, data leaks."""

from __future__ import annotations

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import FubonFetcher, errors
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient


class TestOpenSpaSsrf:
    """Verify redirect allowlist blocks SSRF attempts."""

    @pytest.mark.asyncio
    async def test_redirect_to_internal_ip(self) -> None:
        serial = "abc"
        entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
        async with FubonClient() as client, respx.mock() as mock:
            mock.get(entry).mock(
                return_value=httpx.Response(
                    302, headers={"location": "https://192.168.1.1/steal"}
                )
            )
            with pytest.raises(errors.FubonRedirectError):
                await client.open_spa(serial_key=serial)

    @pytest.mark.asyncio
    async def test_redirect_to_localhost(self) -> None:
        serial = "abc"
        entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
        async with FubonClient() as client, respx.mock() as mock:
            mock.get(entry).mock(
                return_value=httpx.Response(
                    302, headers={"location": "https://localhost/admin"}
                )
            )
            with pytest.raises(errors.FubonRedirectError):
                await client.open_spa(serial_key=serial)

    @pytest.mark.asyncio
    async def test_subdomain_bypass_attempt(self) -> None:
        serial = "abc"
        entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
        async with FubonClient() as client, respx.mock() as mock:
            mock.get(entry).mock(
                return_value=httpx.Response(
                    302,
                    headers={
                        "location": "https://fbmbill.taipeifubon.com.tw.evil.com/"
                    },
                )
            )
            with pytest.raises(errors.FubonRedirectError):
                await client.open_spa(serial_key=serial)


class TestCanFetchSchemeFiltering:
    """Verify can_fetch only accepts HTTPS links."""

    def test_rejects_javascript_scheme(self) -> None:
        html = '<html><a href="javascript:alert(1)">click</a></html>'
        assert FubonFetcher().can_fetch(html) is False

    def test_rejects_data_scheme(self) -> None:
        html = '<html><a href="data:text/html,<script>alert(1)</script>">x</a></html>'
        assert FubonFetcher().can_fetch(html) is False

    def test_rejects_http_scheme(self) -> None:
        html = '<html><a href="http://fbmbill.taipeifubon.com.tw/serial">x</a></html>'
        assert FubonFetcher().can_fetch(html) is False


class TestDataLeakPrevention:
    """Verify sensitive data is not leaked in error messages."""

    @pytest.mark.asyncio
    async def test_jwt_not_in_pdf_error_message(self) -> None:
        """When PDF fetch fails after login, JWT must not appear in error."""
        async with FubonClient() as client, respx.mock() as mock:
            mock.post("https://fbmbill.taipeifubon.com.tw/doLogin").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "errorMsg": None,
                        "jwt": "secret-jwt-token-value",
                        "billPeriod": "11504",
                        "twYearMonth": "11504",
                        "batchPeriod": "20260410",
                        "uniqueIdentifier": "uid",
                    },
                )
            )
            mock.get("https://fbmbill.taipeifubon.com.tw/PDFReportProc").mock(
                return_value=httpx.Response(401, text="unauthorized")
            )
            await client.do_login(
                id_number="A123456789",
                birthday="0850101",
                serial_key="1e79",
                captcha_answer="1234",
                server_token="tok",
            )
            with pytest.raises(errors.FubonSessionError) as exc_info:
                await client.get_bill_pdf(
                    bill_period="11504",
                    batch_period="20260410",
                    uid="uid",
                    tw_year_month="11504",
                )
            assert "secret-jwt-token-value" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_credentials_not_in_login_error(self) -> None:
        """When login fails, national_id must not appear in the error message."""
        async with FubonClient() as client, respx.mock() as mock:
            mock.post("https://fbmbill.taipeifubon.com.tw/doLogin").mock(
                return_value=httpx.Response(
                    200,
                    json={"errorMsg": "身分證字號格式錯誤", "jwt": None},
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
            assert "A123456789" not in str(exc_info.value)
