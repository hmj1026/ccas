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

# -- CATHAY page text fixtures --

CATHAY_FIRST_PAGE_TEXT = (
    "國泰世華銀行\n"
    "信用卡帳單\n"
    "2026年03月份帳單\n"
    "繳費截止日：2026/04/12\n"
    "本期應繳總額：NT$ 4,830\n"
)

CATHAY_NON_CATHAY_PAGE_TEXT = "某某銀行\n信用卡帳單\n帳單月份：2026年03月\n"

CATHAY_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "國泰世華銀行\n信用卡帳單\n2026年03月份帳單\n本期應繳總額：NT$ 4,830\n"
)

CATHAY_SUMMARY_MISSING_TOTAL_TEXT = (
    "國泰世華銀行\n信用卡帳單\n2026年03月份帳單\n繳費截止日：2026/04/12\n"
)

CATHAY_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

CATHAY_TRANSACTION_ROWS = [
    ["03/02", "03/04", "2345", "全家便利商店", "180"],
    ["03/10", "03/12", "2345", "誠品書店", "1,450"],
    ["03/18", "03/20", "6789", "好市多", "3,200"],
]

EXPECTED_CATHAY_BILLING_MONTH = "2026-03"
EXPECTED_CATHAY_TOTAL_AMOUNT = 4830
EXPECTED_CATHAY_DUE_DATE = date(2026, 4, 12)

# -- FUBON page text fixtures --

FUBON_FIRST_PAGE_TEXT = (
    "台北富邦銀行\n"
    "信用卡帳單\n"
    "帳單月份：2026年03月\n"
    "繳費截止日：2026/04/15\n"
    "本期應繳總額：NT$ 15,800\n"
)

FUBON_NON_FUBON_PAGE_TEXT = "某某銀行\n信用卡帳單\n帳單月份：2026年03月\n"

FUBON_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "台北富邦銀行\n信用卡帳單\n帳單月份：2026年03月\n本期應繳總額：NT$ 15,800\n"
)

FUBON_SUMMARY_MISSING_TOTAL_TEXT = (
    "台北富邦銀行\n信用卡帳單\n帳單月份：2026年03月\n繳費截止日：2026/04/15\n"
)

FUBON_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

FUBON_TRANSACTION_ROWS = [
    ["03/05", "03/07", "8899", "全聯福利中心", "680"],
    ["03/10", "03/12", "8899", "台灣大哥大", "499"],
    ["03/15", "03/17", "8899", "誠品書店", "1,250"],
]

FUBON_EXPECTED_BILLING_MONTH = "2026-03"
FUBON_EXPECTED_TOTAL_AMOUNT = 15800
FUBON_EXPECTED_DUE_DATE = date(2026, 4, 15)

# -- ESUN page text fixtures --

ESUN_FIRST_PAGE_TEXT = (
    "玉山銀行 信用卡帳單\n"
    "E.SUN Bank Credit Card Statement\n"
    "\n"
    "2026年03月份帳單\n"
    "繳費截止日：2026/04/18\n"
    "本期應繳總額：NT$ 7,620\n"
)

ESUN_NON_ESUN_PAGE_TEXT = (
    "國泰世華商業銀行 信用卡帳單\nCard Statement\n\n繳費截止日：2026/04/10\n"
)

ESUN_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "玉山銀行 信用卡帳單\n2026年03月份帳單\n本期應繳總額：NT$ 7,620\n"
)

ESUN_SUMMARY_MISSING_TOTAL_TEXT = (
    "玉山銀行 信用卡帳單\n2026年03月份帳單\n繳費截止日：2026/04/18\n"
)

# -- ESUN table row fixtures --

ESUN_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

ESUN_TRANSACTION_ROWS = [
    ["03/01", "03/03", "4567", "全家便利商店", "350"],
    ["03/08", "03/10", "4567", "蝦皮購物", "1,280"],
    ["03/15", "03/17", "8901", "NETFLIX.COM", "590"],
]

# -- Expected parsed values --

EXPECTED_ESUN_BILLING_MONTH = "2026-03"
EXPECTED_ESUN_TOTAL_AMOUNT = 7620
EXPECTED_ESUN_DUE_DATE = date(2026, 4, 18)

# -- TAISHIN page text fixtures --

TAISHIN_FIRST_PAGE_TEXT = (
    "台新銀行 信用卡帳單\n"
    "Taishin Bank Credit Card Statement\n"
    "\n"
    "2026年03月份帳單\n"
    "繳費截止日：2026/04/22\n"
    "本期應繳總額：NT$ 9,380\n"
)

TAISHIN_NON_TAISHIN_PAGE_TEXT = (
    "國泰世華商業銀行 信用卡帳單\nCard Statement\n\n繳費截止日：2026/04/10\n"
)

TAISHIN_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "台新銀行 信用卡帳單\n2026年03月份帳單\n本期應繳總額：NT$ 9,380\n"
)

TAISHIN_SUMMARY_MISSING_TOTAL_TEXT = (
    "台新銀行 信用卡帳單\n2026年03月份帳單\n繳費截止日：2026/04/22\n"
)

# -- TAISHIN table row fixtures --

TAISHIN_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

TAISHIN_TRANSACTION_ROWS = [
    ["03/03", "03/05", "6789", "全聯福利中心", "520"],
    ["03/10", "03/12", "6789", "大潤發", "2,360"],
    ["03/20", "03/22", "1234", "星巴克", "280"],
]

# -- Expected parsed values --

EXPECTED_TAISHIN_BILLING_MONTH = "2026-03"
EXPECTED_TAISHIN_TOTAL_AMOUNT = 9380
EXPECTED_TAISHIN_DUE_DATE = date(2026, 4, 22)

# -- UBOT page text fixtures --

UBOT_FIRST_PAGE_TEXT = (
    "聯邦銀行 信用卡帳單\n"
    "Union Bank of Taiwan Credit Card Statement\n"
    "\n"
    "2026年03月份帳單\n"
    "繳費截止日：2026/04/18\n"
    "本期應繳總額：NT$ 6,530\n"
)

UBOT_NON_UBOT_PAGE_TEXT = (
    "國泰世華商業銀行 信用卡帳單\nCard Statement\n\n繳費截止日：2026/04/10\n"
)

UBOT_SUMMARY_MISSING_DUE_DATE_TEXT = (
    "聯邦銀行 信用卡帳單\n2026年03月份帳單\n本期應繳總額：NT$ 6,530\n"
)

UBOT_SUMMARY_MISSING_TOTAL_TEXT = (
    "聯邦銀行 信用卡帳單\n2026年03月份帳單\n繳費截止日：2026/04/18\n"
)

# -- UBOT table row fixtures --

UBOT_TABLE_HEADER_ROW = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]

UBOT_TRANSACTION_ROWS = [
    ["03/05", "03/07", "3456", "7-ELEVEN", "120"],
    ["03/12", "03/14", "3456", "全聯福利中心", "1,850"],
    ["03/22", "03/24", "7890", "家樂福", "960"],
]

# -- Expected parsed values --

EXPECTED_UBOT_BILLING_MONTH = "2026-03"
EXPECTED_UBOT_TOTAL_AMOUNT = 6530
EXPECTED_UBOT_DUE_DATE = date(2026, 4, 18)
