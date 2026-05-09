"""Unit tests for FubonClient async context manager."""

from __future__ import annotations

import pytest

from ccas.ingestor.fetcher.banks.fubon.client import FubonClient


@pytest.mark.asyncio
async def test_aexit_closes_underlying_httpx_client() -> None:
    client = FubonClient()
    async with client:
        assert not client._client.is_closed
    assert client._client.is_closed


@pytest.mark.asyncio
async def test_aexit_closes_on_exception() -> None:
    client = FubonClient()
    with pytest.raises(ValueError, match="boom"):
        async with client:
            raise ValueError("boom")
    assert client._client.is_closed
