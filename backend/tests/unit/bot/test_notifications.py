"""通知摘要內容測試。"""

from datetime import date
from unittest.mock import MagicMock

from ccas.bot.notifications import (
    render_due_reminder,
    render_new_bill_notification,
    render_parse_failure_notification,
)


def _make_bill(**kwargs) -> MagicMock:
    bill = MagicMock()
    bill.id = kwargs.get("id", 1)
    bill.bank_code = kwargs.get("bank_code", "CTBC")
    bill.billing_month = kwargs.get("billing_month", "2026-03")
    bill.total_amount = kwargs.get("total_amount", 5000)
    bill.due_date = kwargs.get("due_date", date(2026, 4, 15))
    bill.is_paid = kwargs.get("is_paid", False)
    return bill


class TestRenderNewBillNotification:
    """新帳單通知 rendering 測試。"""

    def test_contains_required_fields(self):
        bill = _make_bill(
            billing_month="2026-03",
            total_amount=12000,
            due_date=date(2026, 4, 15),
        )
        result = render_new_bill_notification(bill, "中國信託")
        assert "中國信託" in result
        assert "2026-03" in result
        assert "$12,000" in result
        assert "2026-04-15" in result
        assert "新帳單已解析" in result


class TestRenderDueReminder:
    """到期提醒 rendering 測試。"""

    def test_3_days_reminder(self):
        bill = _make_bill(id=7, total_amount=8000, due_date=date(2026, 4, 10))
        result = render_due_reminder(bill, "國泰世華", days_until_due=3)
        assert "3 天後到期" in result
        assert "$8,000" in result
        assert "/paid 7" in result

    def test_1_day_reminder(self):
        bill = _make_bill(id=7, due_date=date(2026, 4, 10))
        result = render_due_reminder(bill, "國泰世華", days_until_due=1)
        assert "明天到期" in result


class TestRenderParseFailureNotification:
    """解析失敗通知 rendering 測試。"""

    def test_contains_failure_info(self):
        result = render_parse_failure_notification(
            "中國信託", "statement_2026_03.pdf", "PDF 格式無法辨識"
        )
        assert "中國信託" in result
        assert "statement_2026_03.pdf" in result
        assert "PDF 格式無法辨識" in result
        assert "解析失敗" in result

    def test_none_error_reason(self):
        result = render_parse_failure_notification("中國信託", "file.pdf", None)
        assert "未知錯誤" in result
