"""Unit tests for FubonClient.open_spa — SPA session bootstrap."""

from __future__ import annotations

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import errors
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient


@pytest.mark.asyncio
async def test_open_spa_follows_302_and_stores_session_cookie() -> None:
    serial = "1e79254d8b8c42f1a5c15aa54a0c6616"
    entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
    spa_url = f"https://fbmbill.taipeifubon.com.tw/client/pdf/{serial}"

    async with FubonClient() as client, respx.mock() as mock:
        mock.get(entry).mock(
            return_value=httpx.Response(
                302,
                headers={
                    "location": spa_url,
                    "set-cookie": "JSESSIONID=abc123; Path=/",
                },
            )
        )
        mock.get(spa_url).mock(
            return_value=httpx.Response(200, text="<html>SPA</html>")
        )
        await client.open_spa(serial_key=serial)
        assert client._client.cookies.get("JSESSIONID") == "abc123"


@pytest.mark.asyncio
async def test_open_spa_raises_on_non_2xx_status() -> None:
    """A 5xx response on SPA entry should raise FubonSessionError, not retry."""
    serial = "abc"
    entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
    async with FubonClient() as client, respx.mock() as mock:
        mock.get(entry).mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(errors.FubonSessionError, match="unexpected status"):
            await client.open_spa(serial_key=serial)


@pytest.mark.asyncio
async def test_open_spa_raises_on_too_many_redirects() -> None:
    """Six same-host 302s must trip the 5-hop limit."""
    serial = "abc"
    entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
    async with FubonClient() as client, respx.mock() as mock:
        # Every request is a 302 pointing to itself (same host, always allowed).
        mock.get(entry).mock(
            return_value=httpx.Response(302, headers={"location": entry})
        )
        with pytest.raises(errors.FubonSessionError, match="too many redirects"):
            await client.open_spa(serial_key=serial)


@pytest.mark.asyncio
async def test_open_spa_rejects_non_fubon_redirect() -> None:
    serial = "dead"
    entry = f"https://fbmbill.taipeifubon.com.tw/{serial}"
    async with FubonClient() as client, respx.mock() as mock:
        mock.get(entry).mock(
            return_value=httpx.Response(
                302, headers={"location": "https://evil.com/phish"}
            )
        )
        with pytest.raises(errors.FubonRedirectError):
            await client.open_spa(serial_key=serial)
