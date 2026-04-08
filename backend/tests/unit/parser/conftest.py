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


def make_mock_page(text: str, tables: list[list[list[str]]] | None = None):
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

# -- ROC format fixtures (real CTBC PDFs) --

CTBC_ROC_FIRST_PAGE_TEXT = (
    "115 03 1 / 3\n"
    "402\n"
    "115/04 7.7\n"
    "i APP\n"
    ":0800-024365 02-2745-8080\n"
    "80,000\n"
    "115/03/28\n"
    "/ 80,000/ 80,000\n"
    "( ) 2,967 7.7%\n"
    "115/04\n"
    "1,000 ( )\n"
    "https://ctbc.tw/I6R5Wd\n"
)

CTBC_ROC_TXN_PAGE_TEXT = (
    "2 / 3\n"
    "115/03/10 3,292 2,967 0 3,292 0 +2,967\n"
    "115/03/02 -3,292\n"
    "115/02/09 115/02/11 28 6713 TW\n"
    "115/02/12 115/02/23 75 6713 TW\n"
    "115/02/15 115/02/23 228 6713 TW\n"
    "115/03/06 115/03/09 205 6713 TW\n"
)

CTBC_ROC_PAYMENT_PAGE_TEXT = "3 / 3\n03 28 ( )\n$2,967 115 03\n$1,000 115/03/28\n"

EXPECTED_ROC_BILLING_MONTH = "2026-03"
EXPECTED_ROC_TOTAL_AMOUNT = 2967
EXPECTED_ROC_DUE_DATE = date(2026, 3, 28)

# -- Expected parsed values --

EXPECTED_BILLING_MONTH = "2026-03"
EXPECTED_TOTAL_AMOUNT = 12345
EXPECTED_DUE_DATE = date(2026, 4, 15)

# -- 2-page zero-balance bill fixtures (ROC format, no payment slip page) --

CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT = (
    "113 01 1 / 2\n"
    "402\n"
    "113/01 7.58\n"
    "i APP\n"
    "80,000\n"
    "/ 80,000/ 80,000\n"
    "0 7.58%\n"
    "113/01\n"
    "0 ( )\n"
)

CTBC_ROC_ZERO_BALANCE_TXN_PAGE_TEXT = (
    "2 / 2\n113/01/10 460 0 0 460 0 +0\n112/12/28 -460\n(02)2745-8080\n"
)

# -- Garbled CID text (simulates old 2014 PDF embedded-font encoding) --

CTBC_GARBLED_TEXT = (
    "(cid:12)(cid:45)(cid:78)(cid:90)(cid:11)(cid:22)(cid:33)(cid:5)(cid:7)(cid:3)"
)

# -- SINOPAC page text fixtures --

SINOPAC_FIRST_PAGE_TEXT = (
    "永豐銀行 信用卡帳單\n"
    "SinoPac Bank Credit Card Statement\n"
    "\n"
    "2026年03月份帳單\n"
    "繳費截止日：2026/04/20\n"
    "本期應繳總額：NT$ 8,750\n"
)

SINOPAC_NON_SINOPAC_PAGE_TEXT = (
    "國泰世華商業銀行 信用卡帳單\nCard Statement\n\n繳費截止日：2026/04/10\n"
)

SINOPAC_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "永豐銀行 信用卡帳單\n2026年03月份帳單\n本期應繳總額：NT$ 8,750\n"
)

SINOPAC_SUMMARY_MISSING_TOTAL_TEXT = (
    "永豐銀行 信用卡帳單\n2026年03月份帳單\n繳費截止日：2026/04/20\n"
)

# -- SINOPAC table row fixtures --

SINOPAC_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

SINOPAC_TRANSACTION_ROWS = [
    ["03/01", "03/03", "5678", "全聯福利中心", "420"],
    ["03/08", "03/10", "5678", "家樂福", "1,280"],
    ["03/15", "03/17", "9012", "momo購物網", "2,350"],
]

# -- Expected parsed values --

EXPECTED_SINOPAC_BILLING_MONTH = "2026-03"
EXPECTED_SINOPAC_TOTAL_AMOUNT = 8750
EXPECTED_SINOPAC_DUE_DATE = date(2026, 4, 20)
