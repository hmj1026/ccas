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

# -- SINOPAC real-PDF format fixtures (no colon after 繳款截止日, row-based total) --

SINOPAC_REAL_FIRST_PAGE_TEXT = (
    "2026年3月 信用卡電子帳單\n"
    "親愛的卡友 您好\n"
    "感謝您使用本行信用卡消費，信用卡電子帳單如下\n"
    "您的結帳日2026/03/12 您的繳款截止日2026/03/27\n"
    "若您帳單繳款截止日遇例假日時，則可順延至次一營業日繳款。\n"
    "幣別 上期應繳總金額 - 已繳款金額（註一） + 本期新增款項 + 循環利息 + 違約金 "
    "= 本期應繳總金額 本期最低應繳金額\n"
    "臺幣 7,147 7,147 12,579 0 0 12,579 1,311\n"
    "永豐銀行 信用卡\n"
)

EXPECTED_SINOPAC_REAL_BILLING_MONTH = "2026-03"
EXPECTED_SINOPAC_REAL_TOTAL_AMOUNT = 12579
EXPECTED_SINOPAC_REAL_DUE_DATE = date(2026, 3, 27)

SINOPAC_ZERO_BALANCE_FIRST_PAGE_TEXT = (
    "2021年5月 信用卡電子帳單\n"
    "您的結帳日2021/05/12 您的繳款截止日臺幣金額無需繳款\n"
    "臺幣 0 0 0 0 0 0 0\n"
    "永豐銀行 信用卡\n"
)

SINOPAC_REAL_TXN_PAGE_TEXT = (
    "入帳 卡號 外幣 外幣 總費用 分期未到期\n"
    "消費日 帳單說明 臺幣金額\n"
    "起息日 末四碼 折算日 金額 年百分率 金額\n"
    "03/05 03/05 永豐自扣已入帳，謝謝！ -7,147\n"
    "02/18 02/24 4300 悠遊卡自動加值─台北捷 500\n"
    "02/15 02/24 2902 A- 中油－某加油站 975\n"
    "02/28 03/03 2902 WorldGym 1,188\n"
    "您的正卡，本期應繳金額合計 12,579\n"
    "永豐銀行 信用卡\n"
)

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

# -- CATHAY real PDF fixtures --

# 舊版（108年5月）：`以下為您YYY年MM月份` + `繳款截止日(遇假日順延) ROC/MM/DD`
CATHAY_REAL_OLD_TEXT = (
    "親愛的 王小明 客戶您好\n"
    "以下為您108年5月份的信用卡電子帳單\n"
    "帳單結帳日 108/05/15\n"
    "繳款截止日(遇假日順延) 108/06/01\n"
    "本期應繳總額 5,779\n"
    "本期最低應繳總額 2,715\n"
    "信用額度 130,000\n"
)
EXPECTED_CATHAY_REAL_OLD_MONTH = "2019-05"
EXPECTED_CATHAY_REAL_OLD_TOTAL = 5779
EXPECTED_CATHAY_REAL_OLD_DUE = date(2019, 6, 1)

# 中期 grid（112年3月）：pair 行 + `帳款將於`
CATHAY_REAL_GRID_TEXT = (
    "VZ000013-TW-03/18 1/3\n"
    "112/03/15 112/04/01\n"
    "130,000\n"
    "王小明 先生\n"
    "11,478 11,478 34,141 0 0 0 34,141 4,061\n"
    "本期應繳總額 34,141\n"
    "● 您的新臺幣帳款將於 112/04/01 自000-000000****00帳號扣款34,141元整\n"
    "COSTCO多利金 0 518 300 510 308\n"
    "信用卡回饋總覽\n"
)
EXPECTED_CATHAY_REAL_GRID_MONTH = "2023-03"
EXPECTED_CATHAY_REAL_GRID_TOTAL = 34141
EXPECTED_CATHAY_REAL_GRID_DUE = date(2023, 4, 1)

# 新版（115年3月）：`信用卡帳單 YYY年MM月` + `帳款將於 ROC/MM/DD (遇假日順延)`
CATHAY_REAL_NEW_TEXT = (
    "VZ000013-TW-03/18 1/3\n"
    "信用卡帳單 115年3月\n"
    "王小明 先生\n"
    "新臺幣TWD 748 748 1,067 0 0 0 1,067\n"
    "本期應繳總額 1,067\n"
    "◎ 您的新臺幣帳款將於 115/04/01 (遇假日順延)之次一營業日扣款1,067元整\n"
    "國泰世華\n"
    "CUBE App\n"
)
EXPECTED_CATHAY_REAL_NEW_MONTH = "2026-03"
EXPECTED_CATHAY_REAL_NEW_TOTAL = 1067
EXPECTED_CATHAY_REAL_NEW_DUE = date(2026, 4, 1)

# Ancient（106年3月）：無「國泰」字串，僅「多利金」標記
CATHAY_REAL_ANCIENT_TEXT = (
    "親愛的 王小明 客戶您好\n"
    "以下為您 106年 3月份的信用卡電子帳單\n"
    "帳單結帳日 106/03/15\n"
    "繳款截止日(遇假日順延) 106/04/05\n"
    "本期應繳總額 2,833\n"
    "本期最低應繳總額 1,000\n"
    "COSTCO多利金 0 28 0 0 28\n"
    "信用卡消費明細\n"
)
EXPECTED_CATHAY_REAL_ANCIENT_MONTH = "2017-03"
EXPECTED_CATHAY_REAL_ANCIENT_TOTAL = 2833
EXPECTED_CATHAY_REAL_ANCIENT_DUE = date(2017, 4, 5)

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

# -- FUBON real PDF fixtures (ROC year, 繳款期限, 元 suffix) --

FUBON_REAL_PAGE1_TEXT = (
    "第1/3頁\n"
    "本期應繳總額 11,274元\n"
    "帳單年月 信用額度 國內預借現金額度 帳單結帳日 繳款截止日 循環信用利率\n"
    "115/04 200,000 20,000 115/04/08 115/04/24 3.80%\n"
    "台北富邦商業銀行信用卡帳單\n"
    "消費日期 消費說明 入帳日期 外幣折算日/幣別 外幣金額/消費地 台幣金額\n"
    "前期應繳總額 3,793\n"
    "115/03/25 自動扣繳 115/03/26 -3,793\n"
    "MASTER鈦金正卡末４碼5273\n"
    "115/03/08 好市多台中店 115/03/09 TWD 3,098\n"
    "115/03/08 好市多台中店 115/03/09 TWD 339\n"
    "115/03/14 好市多台中店 115/03/16 TWD 100\n"
    "115/03/14 好市多台中店 115/03/16 TWD 2,475\n"
    "115/03/16 好市多台中店 115/03/17 TWD 1,929\n"
    "115/03/31 富邦產物保險股份有限公司 (01/06期) 115/04/02 TWD 2,362\n"
    "115/04/03 好市多台中店 115/04/07 TWD 971\n"
    "本期應繳金額 11,274\n"
)

FUBON_REAL_PAGE2_TEXT = (
    "第2/3頁\n"
    "您本期循環信用年利率為專案利率 3.80％，"
    "適用於115年02月份至115年04月份帳單。\n"
)

EXPECTED_FUBON_REAL_BILLING_MONTH = "2026-04"
EXPECTED_FUBON_REAL_TOTAL_AMOUNT = 11274
EXPECTED_FUBON_REAL_DUE_DATE = date(2026, 4, 24)

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

# -- ESUN real PDF fixtures (民國年 + TWD prefix) --

ESUN_REAL_PAGE0_TEXT = (
    "親愛的 測試客戶 您好：\n"
    "這是您 115年02月 信用卡帳單，感謝您使用電子帳單讓地球更美麗，\n"
    "敬祝招財納福，Smile每一天！ 26,920 元\n"
    "26,920 元 50,000 元\n"
    "115/04/07 7.88%\n"
    "2,692 元 至 115/03\n"
)

ESUN_REAL_PAGE1_TEXT = (
    "繳款幣別 上期未繳餘額 本期新增款項 本期應繳總金額 本期最低應繳金額\n"
    "TWD 0 26,920 26,920 2,692\n"
    "消費日 入帳日 消費明細 消費地 外幣折算日 幣別 金額 繳款幣別 金額 行動支付\n"
    "上期應繳金額： TWD 10,615\n"
    "03/09 感謝您辦理本行自動轉帳繳款！ TWD -10,615\n"
    "本期消費明細：\n"
    "卡號：0000-XXXX-XXXX-0000（Unicard－正卡）\n"
    "02/12 02/23 連加＊連加＊某百貨分店 TWD 142\n"
    "02/13 02/23 連加＊某餐廳分店 TWD 128\n"
)

ESUN_REAL_PAGE2_TEXT = (
    "本期合計： TWD 26,920\n"
    "本期應繳總金額： TWD 26,920\n"
    "※本行將於07日依您的約定帳號：玉山銀行000000XXXX000扣款 26,920元。\n"
)

EXPECTED_ESUN_REAL_BILLING_MONTH = "2026-02"
EXPECTED_ESUN_REAL_TOTAL_AMOUNT = 26920
EXPECTED_ESUN_REAL_DUE_DATE = date(2026, 4, 7)

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

# -- TAISHIN real PDF fixtures (ROC year, text-based layout) --

TAISHIN_REAL_SUMMARY_TEXT = (
    "台新銀行\n"
    "109年 01月 信用卡電子帳單\n"
    "親愛的測試客戶先生您好，以下是您01月份的信用卡帳單\n"
    "帳 務 資 訊\n"
    "帳單結帳日 109/01/12\n"
    "繳款截止日 109/01/30\n"
    "上期應繳總額 43,642\n"
    "-已繳退款總額 18,901\n"
    "=前期餘額 24,741\n"
    "+本期新增款項 10,625\n"
    "=本期累計應繳金額 35,366\n"
    "本期最低應繳金額 5,234\n"
)

TAISHIN_REAL_TRANSACTIONS_TEXT = (
    "消費日 入帳起息日消費明細 新臺幣金額 外幣折算日 消費地 幣別 外幣金額\n"
    "108/12/27 108/12/27 您的付款已收到，謝謝您！ -18,901\n"
    "循環信用利息 322\n"
    "ａＧｏＧｏ iCash 御璽卡 王小明 (卡號末四碼:1234)\n"
    "107/11/16 108/12/19 ＰＣＨＯＭＥ１ 第 14/30 期 993 TW\n"
    "108/12/13 108/12/18 全國加油站文心站 TAICHU 800 TW\n"
    "109/01/02 109/01/06 國外交易服務費－ 3496.00 52\n"
    "109/01/02 109/01/06 ProDirectSoccer newt newton 3,496 0103 GB GBP 87.78\n"
    "109/01/03 109/01/03 １０８年海外當地３％回饋金 -2\n"
    "109/01/04 109/01/07 APPLE.COM/BILL A8838 080009 30 IE\n"
)

EXPECTED_TAISHIN_REAL_BILLING_MONTH = "2020-01"
EXPECTED_TAISHIN_REAL_TOTAL_AMOUNT = 35366
EXPECTED_TAISHIN_REAL_DUE_DATE = date(2020, 1, 30)

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

# -- UBOT real PDF fixtures (unlabeled grid layout) --

UBOT_REAL_SUMMARY_TEXT = (
    "聯邦銀行 信用卡帳單\n"
    "親愛的測試客戶卡友您好!\n"
    "以下為您01月份之信用卡消費帳單：\n"
    "6,850 6,850 4,000,000 優惠注意事項\n"
    "115/02/11 已申請自動轉帳\n"
    "115/01/27 2.1% 起\n"
    "5,839 8,000\n"
    "5,839 3.19% 起\n"
    "6,850 115/07/28 止\n"
)

UBOT_REAL_ZERO_BALANCE_TEXT = (
    "聯邦銀行 信用卡帳單\n"
    "親愛的測試客戶卡友您好!\n"
    "以下為您07月份之信用卡消費帳單：\n"
    "0 0 2,000,000 優惠注意事項\n"
    "無需繳款\n"
    "111/07/27 2.68% 起\n"
)

UBOT_REAL_TRANSACTIONS_TEXT = (
    "入帳日 消費日 消費明細 結匯日 幣別 外幣金額 新臺幣金額\n"
    "上期金額 5,839\n"
    "上期付款金額已收到，謝謝！ -5,839\n"
    "想分就分專案\n"
    "12/28 11/24 某保險公司－保單 02/12 2,603\n"
    "聯邦Ｍ悠遊鈦商卡 －正卡 8000\n"
    "12/30 12/26 某保險公司 ＸＸＸＸＸＸＸＸＸＸＸ TW 12,152\n"
    "12/31 12/26 專案：想分調整某保險公司 ＸＸＸＸ -12,152\n"
    "聯邦悠遊吉鶴卡 －正卡 8602\n"
    "01/07 12/31 PRIME MEMBERSHIP MEGURO-KU JP 01/02 JPY 600.00 120\n"
    "+ 02/23 02/17 台灣大創百貨（股）南港ＬａＬａｐｏｒｔ TW 98\n"
    "總計 6,850\n"
)

EXPECTED_UBOT_REAL_BILLING_MONTH = "2026-01"
EXPECTED_UBOT_REAL_TOTAL_AMOUNT = 6850
EXPECTED_UBOT_REAL_DUE_DATE = date(2026, 2, 11)
