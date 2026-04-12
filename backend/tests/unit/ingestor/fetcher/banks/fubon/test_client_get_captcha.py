"""Unit tests for FubonClient.get_captcha — token + jpeg split."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from ccas.ingestor.fetcher.banks.fubon import errors
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient

FIXTURE = Path(__file__).parents[5] / "fixtures" / "fubon" / "captcha_response.txt"


@pytest.mark.asyncio
async def test_get_captcha_splits_token_and_jpeg() -> None:
    body = FIXTURE.read_text().strip()
    async with FubonClient() as client, respx.mock() as mock:
        mock.get("https://fbmbill.taipeifubon.com.tw/checkImgs/captcha.jpg").mock(
            return_value=httpx.Response(200, text=body)
        )
        token, jpeg_bytes = await client.get_captcha()
        assert token == "tokenABC123"
        assert jpeg_bytes.startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_get_captcha_bad_format_raises() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        mock.get("https://fbmbill.taipeifubon.com.tw/checkImgs/captcha.jpg").mock(
            return_value=httpx.Response(200, text="invalidcontent")
        )
        with pytest.raises(errors.FubonSessionError):
            await client.get_captcha()


@pytest.mark.asyncio
async def test_get_captcha_non_jpeg_payload_raises() -> None:
    """Valid base64 that decodes to non-JPEG bytes must raise."""
    import base64

    # "not a jpeg" base64-encoded — valid base64 but wrong magic bytes
    payload = base64.b64encode(b"not a jpeg").decode("ascii")
    async with FubonClient() as client, respx.mock() as mock:
        mock.get("https://fbmbill.taipeifubon.com.tw/checkImgs/captcha.jpg").mock(
            return_value=httpx.Response(200, text=f"tok,{payload}")
        )
        with pytest.raises(errors.FubonSessionError, match="not a JPEG"):
            await client.get_captcha()


@pytest.mark.asyncio
async def test_get_captcha_bad_base64_raises() -> None:
    async with FubonClient() as client, respx.mock() as mock:
        mock.get("https://fbmbill.taipeifubon.com.tw/checkImgs/captcha.jpg").mock(
            return_value=httpx.Response(200, text="tok,!!!not-base64!!!")
        )
        with pytest.raises(errors.FubonSessionError):
            await client.get_captcha()
