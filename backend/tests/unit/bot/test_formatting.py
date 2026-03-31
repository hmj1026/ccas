"""查詢指令回覆格式的單元測試。

驗證 bill_id 顯示、多銀行分組、空資料處理。
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from ccas.bot.formatting import (
    format_category_summary,
    format_paid_already,
    format_paid_success,
    format_status,
    format_summary,
    format_upcoming,
)


def _make_bill(
    id: int,
    bank_code: str = "CTBC",
    total_amount: int = 5000,
    due_date: date = date(2026, 4, 15),
    is_paid: bool = False,
    billing_month: str = "2026-03",
) -> MagicMock:
    bill = MagicMock()
    bill.id = id
    bill.bank_code = bank_code
    bill.total_amount = total_amount
    bill.due_date = due_date
    bill.is_paid = is_paid
    bill.billing_month = billing_month
    return bill


BANK_NAMES = {"CTBC": "中國信託", "CATHAY": "國泰世華"}


class TestFormatStatus:
    """format_status 測試。"""

    def test_no_bills(self):
        result = format_status([], BANK_NAMES)
        assert "沒有" in result

    def test_single_bank_shows_bill_id(self):
        bills = [_make_bill(id=42, bank_code="CTBC")]
        result = format_status(bills, BANK_NAMES)
        assert "#42" in result
        assert "中國信託" in result

    def test_multi_bank_grouping(self):
        bills = [
            _make_bill(id=1, bank_code="CTBC", total_amount=3000),
            _make_bill(id=2, bank_code="CATHAY", total_amount=7000),
        ]
        result = format_status(bills, BANK_NAMES)
        assert "中國信託" in result
        assert "國泰世華" in result
        assert "小計 $3,000" in result
        assert "小計 $7,000" in result
        assert "合計：$10,000" in result

    def test_paid_mark_display(self):
        bills = [
            _make_bill(id=1, is_paid=True),
            _make_bill(id=2, is_paid=False),
        ]
        result = format_status(bills, BANK_NAMES)
        assert "[v]" in result
        assert "[x]" in result

    def test_filter_label_in_header(self):
        bills = [_make_bill(id=1)]
        result = format_status(bills, BANK_NAMES, filter_label="未繳")
        assert "未繳" in result


class TestFormatUpcoming:
    """format_upcoming 測試。"""

    def test_no_upcoming(self):
        result = format_upcoming([], BANK_NAMES)
        assert "沒有即將到期" in result

    def test_shows_days_and_bill_id(self):
        bills = [_make_bill(id=5, due_date=date.today())]
        result = format_upcoming(bills, BANK_NAMES)
        assert "#5" in result
        assert "天後" in result


class TestFormatSummary:
    """format_summary 測試。"""

    def test_no_data(self):
        result = format_summary([], BANK_NAMES, "2026-03")
        assert "沒有帳單資料" in result

    def test_shows_paid_count(self):
        bills = [
            _make_bill(id=1, is_paid=True),
            _make_bill(id=2, is_paid=False),
        ]
        result = format_summary(bills, BANK_NAMES, "2026-03")
        assert "已繳 1/2" in result


class TestFormatCategorySummary:
    """format_category_summary 測試。"""

    def test_no_data(self):
        result = format_category_summary([], "2026-03")
        assert "沒有消費資料" in result

    def test_shows_percentages(self):
        rows = [("餐飲", 6000), ("交通", 4000)]
        result = format_category_summary(rows, "2026-03")
        assert "餐飲" in result
        assert "60.0%" in result
        assert "40.0%" in result
        assert "合計：$10,000" in result


class TestFormatPaid:
    """format_paid_success / format_paid_already 測試。"""

    def test_paid_success(self):
        bill = _make_bill(id=10, bank_code="CTBC", total_amount=3000)
        result = format_paid_success(bill, BANK_NAMES)
        assert "#10" in result
        assert "已繳" in result
        assert "中國信託" in result

    def test_paid_already(self):
        bill = _make_bill(id=10, bank_code="CTBC")
        result = format_paid_already(bill, BANK_NAMES)
        assert "#10" in result
        assert "已經是已繳" in result
