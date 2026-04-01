"""CTBC parser unit test fixtures."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from ccas.parser.registry import registry

# -- Registry isolation --


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset global parser registry before each test."""
    registry.clear()
    yield
    registry.clear()


# -- Shared mock helpers --


def make_mock_page(
    text: str, tables: list[list[list[str]]] | None = None
):
    """Create a mock pdfplumber Page with extract_text() and extract_tables()."""
    page = MagicMock()
    page.extract_text.return_value = text
    page.extract_tables.return_value = tables or []
    return page


# -- CTBC page text fixtures --

CTBC_FIRST_PAGE_TEXT = (
    "中國信託商業銀行 信用卡帳單\n"
    "Card Statement\n"
    "\n"
    "繳費截止日：2026/04/15\n"
    "本期應繳總額：NT$ 12,345\n"
    "帳單結帳日：2026/03/25\n"
    "帳單月份：2026年03月\n"
)

CTBC_NON_CTBC_PAGE_TEXT = (
    "國泰世華商業銀行 信用卡帳單\nCard Statement\n\n繳費截止日：2026/04/10\n"
)

CTBC_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "中國信託商業銀行 信用卡帳單\n"
    "Card Statement\n"
    "\n"
    "本期應繳總額：NT$ 12,345\n"
    "帳單月份：2026年03月\n"
)

CTBC_SUMMARY_MISSING_TOTAL_TEXT = (
    "中國信託商業銀行 信用卡帳單\n"
    "Card Statement\n"
    "\n"
    "繳費截止日：2026/04/15\n"
    "帳單月份：2026年03月\n"
)

# -- Table row fixtures (simulate pdfplumber table extraction) --

# Each row is a list of cell strings, matching pdfplumber's extract_tables() output.
# Columns: 交易日, 入帳日, 卡號末四碼, 交易說明/商家, 金額(TWD)
CTBC_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

CTBC_TRANSACTION_ROWS = [
    ["03/01", "03/03", "1234", "全聯福利中心", "350"],
    ["03/05", "03/07", "1234", "台灣大車隊", "185"],
    ["03/10", "03/12", "5678", "NETFLIX.COM", "390"],
]

CTBC_FOREIGN_TRANSACTION_ROW = [
    "03/15",
    "03/18",
    "1234",
    "AMAZON.COM USD 12.99",
    "403",
]

CTBC_INSTALLMENT_ROW = [
    "03/20",
    "03/22",
    "5678",
    "APPLE STORE 分期 2/12",
    "1,250",
]

# -- Expected parsed values --

EXPECTED_BILLING_MONTH = "2026-03"
EXPECTED_TOTAL_AMOUNT = 12345
EXPECTED_DUE_DATE = date(2026, 4, 15)
