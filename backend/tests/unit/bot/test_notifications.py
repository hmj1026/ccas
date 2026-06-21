"""ccas.bot.notifications 高階通知派發層測試。

notify_* 接收純量參數（非 Bill ORM），組合 render_* + send_message。
此處驗證：送出的訊息文字正確、prefix 行為、以及純量簽章不觸碰 ORM。
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from ccas.bot.notifications import (
    notify_due_reminder,
    notify_new_bill,
    notify_parse_failure,
)


@pytest.mark.asyncio
class TestNotifyNewBill:
    async def test_sends_rendered_new_bill_text(self):
        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.bot.notifications.send_message", mock_send):
            await notify_new_bill(
                "token",
                "chat",
                bank_name="中國信託",
                billing_month="2026-03",
                total_amount=12000,
                due_date=date(2026, 4, 15),
                bill_id=7,
            )
        mock_send.assert_awaited_once()
        assert mock_send.await_args is not None
        bot_token, chat_id, text = mock_send.await_args.args
        assert bot_token == "token"
        assert chat_id == "chat"
        assert "中國信託" in text
        assert "2026-03" in text
        assert "$12,000" in text
        assert "2026-04-15" in text


@pytest.mark.asyncio
class TestNotifyDueReminder:
    async def test_sends_rendered_due_reminder_text(self):
        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.bot.notifications.send_message", mock_send):
            await notify_due_reminder(
                "token",
                "chat",
                bank_name="國泰世華",
                total_amount=8000,
                due_date=date(2026, 4, 10),
                bill_id=3,
                days_until_due=3,
            )
        assert mock_send.await_args is not None
        _, _, text = mock_send.await_args.args
        assert "國泰世華" in text
        assert "$8,000" in text
        assert "3 天後到期" in text
        assert "/paid 3" in text
        assert not text.startswith("[測試]")

    async def test_prefix_prepended_for_test_push(self):
        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.bot.notifications.send_message", mock_send):
            await notify_due_reminder(
                "token",
                "chat",
                bank_name="國泰世華",
                total_amount=8000,
                due_date=date(2026, 4, 10),
                bill_id=3,
                days_until_due=1,
                prefix="[測試] ",
            )
        assert mock_send.await_args is not None
        _, _, text = mock_send.await_args.args
        assert text.startswith("[測試] ")
        assert "明天到期" in text


@pytest.mark.asyncio
class TestNotifyParseFailure:
    async def test_sends_rendered_failure_text(self):
        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.bot.notifications.send_message", mock_send):
            await notify_parse_failure(
                "token",
                "chat",
                bank_name="玉山",
                filename="statement.pdf",
                error_reason="PDF 格式無法辨識",
            )
        assert mock_send.await_args is not None
        _, _, text = mock_send.await_args.args
        assert "玉山" in text
        assert "statement.pdf" in text
        assert "PDF 格式無法辨識" in text
