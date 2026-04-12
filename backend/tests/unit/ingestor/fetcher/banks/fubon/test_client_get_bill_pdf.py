"""Unit tests for FubonClient.get_main_info + get_bill_pdf."""

from __future__ import annotations

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import errors
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient


@pytest.mark.asyncio
async def test_get_main_info_returns_cached_from_do_login() -> None:
    """Primary path: doLogin cached main_info, no HTTP round-trip."""
    async with FubonClient() as client:
        client._jwt = "jwt-abc"
        client._main_info = {
            "billPeriod": "11504",
            "batchPeriod": "20260410",
            "uniqueIdentifier": "uid123",
            "twYearMonth": "11504",
        }
        result = await client.get_main_info()
        assert result["billPeriod"] == "11504"
        assert result["uniqueIdentifier"] == "uid123"


@pytest.mark.asyncio
async def test_get_main_info_without_cache_raises() -> None:
    """Cache empty → RuntimeError (do_login must populate main_info)."""
    async with FubonClient() as client:
        client._jwt = "jwt-abc"
        client._main_info = None
        with pytest.raises(RuntimeError, match="main_info"):
            await client.get_main_info()


@pytest.mark.asyncio
async def test_get_bill_pdf_sends_authorization_raw_not_bearer() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        client._jwt = "jwt-xyz"
        route = mock.get("https://fbmbill.taipeifubon.com.tw/PDFReportProc").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4\n%fake\n")
        )
        result = await client.get_bill_pdf(
            bill_period="11504",
            batch_period="20260410",
            uid="uid123",
            tw_year_month="11504",
        )
        assert route.called
        req = route.calls.last.request
        assert req.headers.get("Authorization") == "jwt-xyz"
        assert "Bearer" not in (req.headers.get("Authorization") or "")
        assert req.url.params["billPeriod"] == "11504"
        assert req.url.params["batchPeriod"] == "20260410"
        assert req.url.params["id"] == "uid123"
        assert req.url.params["twYearMonth"] == "11504"
        assert result.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_get_bill_pdf_requires_jwt() -> None:
    async with FubonClient() as client:
        assert client._jwt is None
        with pytest.raises(RuntimeError, match="jwt"):
            await client.get_bill_pdf(
                bill_period="11504",
                batch_period="20260410",
                uid="uid123",
                tw_year_month="11504",
            )


@pytest.mark.asyncio
async def test_get_bill_pdf_non_200_raises_session_error() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        client._jwt = "jwt-abc"
        mock.get("https://fbmbill.taipeifubon.com.tw/PDFReportProc").mock(
            return_value=httpx.Response(401, text="unauthorized")
        )
        with pytest.raises(errors.FubonSessionError, match="PDFReportProc http 401"):
            await client.get_bill_pdf(
                bill_period="11504",
                batch_period="20260410",
                uid="uid123",
                tw_year_month="11504",
            )


@pytest.mark.asyncio
async def test_get_bill_pdf_non_pdf_content_raises_session_error() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        client._jwt = "jwt-abc"
        mock.get("https://fbmbill.taipeifubon.com.tw/PDFReportProc").mock(
            return_value=httpx.Response(200, content=b"<html>error</html>")
        )
        with pytest.raises(errors.FubonSessionError, match="not a PDF"):
            await client.get_bill_pdf(
                bill_period="11504",
                batch_period="20260410",
                uid="uid123",
                tw_year_month="11504",
            )


@pytest.mark.asyncio
async def test_get_main_info_returns_defensive_copy() -> None:
    """Mutating the returned dict must not affect the cached original."""
    async with FubonClient() as client:
        client._main_info = {
            "billPeriod": "11504",
            "batchPeriod": "20260410",
            "uniqueIdentifier": "uid",
            "twYearMonth": "11504",
        }
        result = await client.get_main_info()
        result["billPeriod"] = "MUTATED"
        assert client._main_info["billPeriod"] == "11504"
