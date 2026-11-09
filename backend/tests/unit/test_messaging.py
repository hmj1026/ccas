"""ccas.messaging 共用模組測試。

涵蓋 send_message 的 retry 行為（429/5xx 重試、成功回應、
非暫時性錯誤不重試）與 render_* 純函式訊息格式。
"""

from datetime import date

import httpx
import pytest

from ccas.messaging import (
    ParseFailureLine,
    render_due_reminder,
    render_new_bill_notification,
    render_parse_failure_notification,
    send_message,
)


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


class TestRenderNewBillNotification:
    """新帳單通知 rendering 測試。"""

    def test_contains_required_fields(self):
        result = render_new_bill_notification(
            "中國信託",
            billing_month="2026-03",
            total_amount=12000,
            due_date=date(2026, 4, 15),
        )
        assert "中國信託" in result
        assert "2026-03" in result
        assert "$12,000" in result
        assert "2026-04-15" in result
        assert "新帳單已解析" in result


class TestRenderDueReminder:
    """到期提醒 rendering 測試。"""

    def test_3_days_reminder(self):
        result = render_due_reminder(
            "國泰世華",
            total_amount=8000,
            due_date=date(2026, 4, 10),
            bill_id=7,
            days_until_due=3,
        )
        assert "3 天後到期" in result
        assert "$8,000" in result
        assert "/paid 7" in result

    def test_1_day_reminder(self):
        result = render_due_reminder(
            "國泰世華",
            total_amount=8000,
            due_date=date(2026, 4, 10),
            bill_id=7,
            days_until_due=1,
        )
        assert "明天到期" in result


class TestRenderParseFailureNotification:
    """解析失敗通知 rendering 測試（多份帳單附件合併為一則訊息）。"""

    def test_contains_failure_info(self):
        result = render_parse_failure_notification(
            [ParseFailureLine("中國信託", "statement_2026_03.pdf", "PDF 格式無法辨識")]
        )
        assert "中國信託" in result
        assert "statement_2026_03.pdf" in result
        assert "PDF 格式無法辨識" in result
        assert "解析失敗" in result

    def test_none_error_reason(self):
        result = render_parse_failure_notification(
            [ParseFailureLine("中國信託", "file.pdf", None)]
        )
        assert "未知錯誤" in result

    def test_lists_every_failure_with_count(self):
        result = render_parse_failure_notification(
            [
                ParseFailureLine("中國信託", "a.pdf", "x"),
                ParseFailureLine("玉山", "b.pdf", "y"),
                ParseFailureLine("台新", "c.pdf", "z"),
            ]
        )
        assert "3 份" in result
        for name in ("a.pdf", "b.pdf", "c.pdf", "玉山", "台新"):
            assert name in result

    def test_truncates_long_error_reason(self):
        result = render_parse_failure_notification(
            [ParseFailureLine("中國信託", "a.pdf", "E" * 500)]
        )
        assert "E" * 200 in result
        assert "E" * 201 not in result

    def test_caps_list_at_twenty_entries(self):
        failures = [ParseFailureLine("中國信託", f"f{i}.pdf", "x") for i in range(25)]
        result = render_parse_failure_notification(failures)
        assert "f19.pdf" in result
        assert "f20.pdf" not in result
        assert "…及其他 5 份" in result
        assert "25 份" in result
        assert len(result) < 4096
