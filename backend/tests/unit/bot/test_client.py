"""Telegram API client retry 行為的單元測試。

驗證 429/5xx 重試、成功回應、非暫時性錯誤不重試。
"""

import httpx
import pytest

from ccas.bot.client import send_message


class _MockTransport(httpx.AsyncBaseTransport):
    """可程式化的 mock transport，依序回傳指定的 status codes。"""

    def __init__(self, responses: list[int]):
        self._responses = list(responses)
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._call_count += 1
        status = self._responses.pop(0) if self._responses else 200
        if status == 200:
            return httpx.Response(
                status_code=200,
                json={"ok": True, "result": {"message_id": 1}},
                request=request,
            )
        return httpx.Response(
            status_code=status,
            json={"ok": False, "description": f"Error {status}"},
            request=request,
        )


def _make_client(transport: _MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
class TestSendMessageRetry:
    """send_message retry 行為測試。"""

    async def test_success_on_first_try(self):
        transport = _MockTransport([200])
        result = await send_message(
            "token",
            "123",
            "hello",
            base_delay=0,
            http_client=_make_client(transport),
        )
        assert result["ok"] is True
        assert transport.call_count == 1

    async def test_retry_on_429(self):
        transport = _MockTransport([429, 200])
        result = await send_message(
            "token",
            "123",
            "hello",
            max_retries=3,
            base_delay=0,
            http_client=_make_client(transport),
        )
        assert result["ok"] is True
        assert transport.call_count == 2

    async def test_retry_on_5xx(self):
        transport = _MockTransport([503, 502, 200])
        result = await send_message(
            "token",
            "123",
            "hello",
            max_retries=3,
            base_delay=0,
            http_client=_make_client(transport),
        )
        assert result["ok"] is True
        assert transport.call_count == 3

    async def test_no_retry_on_400(self):
        transport = _MockTransport([400])
        with pytest.raises(httpx.HTTPStatusError):
            await send_message(
                "token",
                "123",
                "hello",
                max_retries=3,
                base_delay=0,
                http_client=_make_client(transport),
            )
        assert transport.call_count == 1

    async def test_no_retry_on_403(self):
        transport = _MockTransport([403])
        with pytest.raises(httpx.HTTPStatusError):
            await send_message(
                "token",
                "123",
                "hello",
                max_retries=3,
                base_delay=0,
                http_client=_make_client(transport),
            )
        assert transport.call_count == 1

    async def test_exhausted_retries_raises(self):
        transport = _MockTransport([500, 500, 500, 500])
        with pytest.raises(httpx.HTTPStatusError):
            await send_message(
                "token",
                "123",
                "hello",
                max_retries=3,
                base_delay=0,
                http_client=_make_client(transport),
            )
        assert transport.call_count == 4  # 1 initial + 3 retries
