"""國泰世華銀行 (Cathay United Bank) v1 信用卡帳單 parser。

使用 pdfplumber 解析帳單 PDF，提取帳單摘要與交易明細。
支援西元年日期格式（YYYY/MM/DD），若遇民國年則自動轉換。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pdfplumber
import pdfplumber.page

from ccas.parser.base import BankParser, ParseError
from ccas.parser.refund_utils import is_refund_merchant, parse_amount_cell
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

# 真實 PDF page 0 收件人姓名常被 CID 字型遮蔽，且部分年份的 PDF 文字中「國泰世華」
# 被拆分成「國泰」「世華」兩段或完全消失。使用兩組鍵詞做後援：
# - 主要（112+）：「國泰」+「信用卡」
# - 備援（106 ancient）：「多利金」+「信用卡」（COSTCO 聯名卡回饋名稱，國泰世華獨有）
_CATHAY_KEYWORDS_PRIMARY = ("國泰", "信用卡")
_CATHAY_KEYWORDS_FALLBACK = ("多利金", "信用卡")

# -- Summary extraction patterns --

# 帳單月份：2026年03月 or 帳單月份：2026/03
_RE_BILLING_MONTH = re.compile(r"(\d{4})\s*[年/]\s*(\d{1,2})\s*月?\s*(?:份|月)")
# 繳費截止日：2026/04/15 or 繳款截止日：2026-04-15
_RE_DUE_DATE = re.compile(r"繳[費款]截止日[：:]\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
# 本期應繳總額：NT$ 12,345（最精確，優先採用以避免誤抓「本期最低應繳金額」）。
_RE_TOTAL_AMOUNT_REAL = re.compile(r"本期應繳總額[：:]?\s*(?:NT\$?\s*)?([\d,]+)")
# 泛用後援：應繳總額／應繳金額。負向預看排除「最低應繳…」，避免在「最低應繳金額」
# 早於「本期應繳總額」出現時誤抓最低應繳值。
_RE_TOTAL_AMOUNT = re.compile(
    r"(?<!最低)應繳[總金][額額][：:]?\s*(?:NT\$?\s*)?([\d,]+)"
)

# -- ROC date support --

_ROC_OFFSET = 1911
_RE_ROC_DUE_DATE = re.compile(
    r"繳[費款]截止日[：:]\s*(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})"
)
# 真實 PDF：`繳款截止日(遇假日順延) 108/06/01`（無冒號，括號後空白）
_RE_ROC_DUE_DATE_PAREN = re.compile(
    r"繳款截止日\s*\(遇假日順延\)\s*(\d{2,3})/(\d{1,2})/(\d{1,2})"
)
# 真實 PDF（112+）：`帳款將於 115/04/01 (遇假日順延)` 或 `帳款將於 108/6/1 自013-...`
_RE_ROC_DUE_DATE_DEBIT = re.compile(r"帳款將於\s*(\d{2,3})/(\d{1,2})/(\d{1,2})")
_RE_ROC_BILLING_MONTH = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月")
# 真實 PDF：`以下為您108年5月份的信用卡電子帳單`
_RE_ROC_BILLING_MONTH_REAL = re.compile(r"以下為您(\d{2,3})年(\d{1,2})月份")
# 真實 PDF（115+）：`信用卡帳單 115年3月`
_RE_ROC_BILLING_MONTH_HEADER = re.compile(r"信用卡帳單\s*(\d{2,3})年\s*(\d{1,2})月")
# 真實 PDF（112+）grid 佈局：結帳日與繳款截止日並排 `112/03/15 112/04/01`
_RE_ROC_CLOSING_DUE_PAIR = re.compile(
    r"^(\d{2,3})/(\d{1,2})/\d{1,2}\s+(\d{2,3})/(\d{1,2})/\d{1,2}\s*$", re.MULTILINE
)

# -- Transaction patterns --

_TRANSACTION_HEADER_DATE_KEYWORDS = ("交易日", "消費日", "日期")
_TRANSACTION_HEADER_AMOUNT_KEYWORDS = ("金額", "新臺幣金額", "款項")

# Sections that follow the consumption table and share its date+amount shape,
# so text-line regex would otherwise mis-capture their summary rows.
_NON_TRANSACTION_SECTION_ANCHORS = (
    "帳單分期",
    "紅利點數",
    "優惠回饋",
    "本期回饋",
    "累積紅利",
    "循環信用",
)

_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")


def _crop_transaction_section(text: str) -> str:
    """Truncate ``text`` at the first non-transaction section anchor."""
    earliest = len(text)
    for anchor in _NON_TRANSACTION_SECTION_ANCHORS:
        idx = text.find(anchor)
        if idx != -1 and idx < earliest:
            earliest = idx
    return text[:earliest]


# Text line-based transactions:
# YYYY/MM/DD  YYYY/MM/DD  MERCHANT  AMOUNT  (or similar)
# Also handle MM/DD format in some layouts
_RE_TRANSACTION_LINE = re.compile(
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # trans_date
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # posting_date
    r"(.+?)\s+"  # merchant
    r"([\d,]+)\s*$",  # amount
    re.MULTILINE,
)

# Simpler line: date merchant amount (no posting date)
_RE_TRANSACTION_LINE_SIMPLE = re.compile(
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # trans_date
    r"(.+?)\s+"  # merchant
    r"([\d,]+)\s*$",  # amount
    re.MULTILINE,
)


def _parse_date(raw: str, billing_year: int, billing_month_num: int = 0) -> date | None:
    """Parse a date string in various formats (YYYY/MM/DD, MM/DD, ROC YYY/MM/DD).

    When ``billing_month_num`` is provided and a 2-part MM/DD month exceeds it,
    the year is shifted back by one to handle cross-year billing cycles (a
    January statement that lists the prior December's transactions).
    """
    parts = raw.split("/")
    if len(parts) != 3 and len(parts) != 2:
        return None

    try:
        if len(parts) == 2:
            # MM/DD format
            mm = int(parts[0])
            cross_year = billing_month_num > 0 and mm > billing_month_num
            year = billing_year - 1 if cross_year else billing_year
            return date(year, mm, int(parts[1]))
        year_part = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        if year_part < 200:
            # ROC year
            year_part += _ROC_OFFSET
        return date(year_part, month, day)
    except (ValueError, IndexError):
        return None


def _parse_mmdd(raw: str, billing_year: int, billing_month_num: int = 0) -> date | None:
    """Parse an 'MM/DD' string into a Python date using the given year."""
    match = _RE_DATE_MMDD.match(raw)
    if not match:
        return None
    mm = int(match.group(1))
    cross_year = billing_month_num > 0 and mm > billing_month_num
    year = billing_year - 1 if cross_year else billing_year
    return date(year, mm, int(match.group(2)))


class CathayV1Parser(BankParser):
    """國泰世華銀行信用卡帳單 v1 parser。"""

    bank_code = "CATHAY"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is a Cathay United Bank credit card statement.

        掃描全部頁面文字，因真實 PDF page 0 的收件人姓名常被 CID 字型遮蔽，
        導致「國泰世華」關鍵字僅出現在後續頁面。
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                return self._identify(text)
        except Exception:
            logger.debug("無法開啟 PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse Cathay United Bank statement PDF into structured result."""
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages
            billing_month, total_amount, due_date = self._extract_summary(pages)
            billing_year = int(billing_month.split("-")[0])
            billing_month_num = int(billing_month.split("-")[1])
            transactions = self._extract_transactions(
                pages, billing_year, billing_month_num
            )

        return ParseResult(
            bank_code=self.bank_code,
            billing_month=billing_month,
            total_amount=total_amount,
            due_date=due_date,
            transactions=transactions,
        )

    def _identify(self, text: str) -> bool:
        """Check if text contains Cathay United Bank statement markers."""
        return all(kw in text for kw in _CATHAY_KEYWORDS_PRIMARY) or all(
            kw in text for kw in _CATHAY_KEYWORDS_FALLBACK
        )

    def _extract_summary(
        self, pages: list[pdfplumber.page.Page]
    ) -> tuple[str, int, date]:
        """Extract billing_month, total_amount, due_date from page text.

        Raises:
            ParseError: If any mandatory summary field is missing.
        """
        full_text = "\n".join(page.extract_text() or "" for page in pages)

        billing_month = self._extract_billing_month(full_text)
        if billing_month is None:
            raise ParseError("帳單摘要缺失", reason="找不到帳單月份")

        due_date = self._extract_due_date(full_text)
        if due_date is None:
            raise ParseError("帳單摘要缺失", reason="找不到繳費截止日")

        total_amount = self._extract_total_amount(full_text)
        if total_amount is None:
            raise ParseError("帳單摘要缺失", reason="找不到應繳總額")

        return billing_month, total_amount, due_date

    def _extract_billing_month(self, text: str) -> str | None:
        """Extract billing month from text."""
        # Try Western year first
        match = _RE_BILLING_MONTH.search(text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}"
        # 真實 PDF 錨點（精確度優先於泛用 ROC regex）
        match = _RE_ROC_BILLING_MONTH_REAL.search(text)
        if match is None:
            match = _RE_ROC_BILLING_MONTH_HEADER.search(text)
        if match:
            roc_year = int(match.group(1))
            month = int(match.group(2))
            ad_year = roc_year + _ROC_OFFSET
            return f"{ad_year}-{month:02d}"
        # Grid 佈局：結帳日與繳款截止日並排，第一組即結帳日
        pair_match = _RE_ROC_CLOSING_DUE_PAIR.search(text)
        if pair_match:
            roc_year = int(pair_match.group(1))
            month = int(pair_match.group(2))
            if roc_year < 200:
                ad_year = roc_year + _ROC_OFFSET
                return f"{ad_year}-{month:02d}"
        # 最後 fallback 至泛用 ROC `YYY年MM月` 格式
        match = _RE_ROC_BILLING_MONTH.search(text)
        if match:
            roc_year = int(match.group(1))
            month = int(match.group(2))
            ad_year = roc_year + _ROC_OFFSET
            return f"{ad_year}-{month:02d}"
        return None

    def _extract_due_date(self, text: str) -> date | None:
        """Extract due date from text."""
        # Try Western date first
        match = _RE_DUE_DATE.search(text)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        # Try ROC date with labelled formats in priority order
        for pattern in (
            _RE_ROC_DUE_DATE,
            _RE_ROC_DUE_DATE_PAREN,
            _RE_ROC_DUE_DATE_DEBIT,
        ):
            match = pattern.search(text)
            if match is None:
                continue
            roc_year = int(match.group(1))
            if roc_year < 200:
                return date(
                    roc_year + _ROC_OFFSET,
                    int(match.group(2)),
                    int(match.group(3)),
                )
        return None

    def _extract_total_amount(self, text: str) -> int | None:
        """Extract total payable amount from text.

        Prefers the precise ``本期應繳總額`` marker so we never capture the
        nearby ``本期最低應繳金額`` (minimum payment) when it happens to appear
        first in the page text.
        """
        match = _RE_TOTAL_AMOUNT_REAL.search(text)
        if match:
            return int(match.group(1).replace(",", ""))
        match = _RE_TOTAL_AMOUNT.search(text)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

    def _extract_transactions(
        self,
        pages: list[pdfplumber.page.Page],
        billing_year: int,
        billing_month_num: int = 0,
    ) -> tuple[TransactionItem, ...]:
        """Extract transaction items from all pages.

        Tries table extraction first, then text line parsing.
        """
        items = _extract_transactions_table(pages, billing_year, billing_month_num)
        if items:
            return tuple(items)

        items = _extract_transactions_text(pages, billing_year, billing_month_num)
        return tuple(items)


# -- Table extraction helpers --


def _extract_transactions_table(
    pages: list[pdfplumber.page.Page],
    billing_year: int,
    billing_month_num: int = 0,
) -> list[TransactionItem]:
    """Extract transactions from tables."""
    items: list[TransactionItem] = []
    for page in pages:
        for table in page.extract_tables():
            if not _is_transaction_table(table):
                continue
            for row in table[1:]:
                item = _parse_transaction_row(row, billing_year, billing_month_num)
                if item is not None:
                    items.append(item)
    return items


def _is_transaction_table(table: list[list[str | None]]) -> bool:
    """Return True if header has both a date-like and an amount-like keyword."""
    if not table:
        return False
    header = [str(cell or "") for cell in table[0]]
    header_text = " ".join(header)
    has_date = any(kw in header_text for kw in _TRANSACTION_HEADER_DATE_KEYWORDS)
    has_amount = any(kw in header_text for kw in _TRANSACTION_HEADER_AMOUNT_KEYWORDS)
    if not (has_date and has_amount):
        return False
    # Installment detail tables also match date+amount; the "分期" token
    # disambiguates them from regular consumption tables.
    if "分期" in header_text:
        return False
    return True


def _parse_transaction_row(
    row: list[str | None],
    year: int,
    billing_month_num: int = 0,
) -> TransactionItem | None:
    """Parse a single table row into a TransactionItem.

    Expected columns: [trans_date (MM/DD), posting_date (MM/DD), card_last4,
    merchant, amount]. Rows with fewer than 5 columns fall back to
    [trans_date, merchant, amount] for 3-column tables.
    """
    try:
        cells = [str(cell or "").strip() for cell in row]
        if len(cells) >= 5:
            raw_trans_date = cells[0]
            raw_posting_date = cells[1]
            raw_card_last4 = cells[2]
            merchant = cells[3]
            raw_amount = cells[4]

            trans_date = _parse_mmdd(raw_trans_date, year, billing_month_num)
            if trans_date is None:
                trans_date = _parse_date(raw_trans_date, year, billing_month_num)
            if trans_date is None:
                logger.warning("跳過無法解析交易日的行: %s", cells)
                return None

            amount = parse_amount_cell(raw_amount)
            if is_refund_merchant(merchant):
                amount = -abs(amount)
            posting_date = _parse_mmdd(raw_posting_date, year, billing_month_num)
            if posting_date is None:
                posting_date = _parse_date(raw_posting_date, year, billing_month_num)
            is_valid_card = raw_card_last4.isdigit() and len(raw_card_last4) == 4
            card_last4 = raw_card_last4 if is_valid_card else None

            return TransactionItem(
                trans_date=trans_date,
                merchant=merchant,
                amount=amount,
                posting_date=posting_date,
                card_last4=card_last4,
            )
        if len(cells) >= 3:
            # Minimal: trans_date, merchant, amount
            raw_trans_date = cells[0]
            merchant = cells[1]
            raw_amount = cells[2]

            trans_date = _parse_mmdd(raw_trans_date, year, billing_month_num)
            if trans_date is None:
                trans_date = _parse_date(raw_trans_date, year, billing_month_num)
            if trans_date is None:
                logger.warning("跳過無法解析交易日的行: %s", cells)
                return None

            amount = parse_amount_cell(raw_amount)
            if is_refund_merchant(merchant):
                amount = -abs(amount)
            return TransactionItem(
                trans_date=trans_date,
                merchant=merchant,
                amount=amount,
            )

        logger.warning("跳過欄位不足的交易行: %s", cells)
        return None
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", row)
        return None


# -- Text line extraction helpers --


def _extract_transactions_text(
    pages: list[pdfplumber.page.Page],
    billing_year: int,
    billing_month_num: int = 0,
) -> list[TransactionItem]:
    """Extract transactions from text lines.

    Full format (date date merchant amount) is tried across all pages first;
    only if no page yields any full-format row do we fall back to simple format
    across all pages. The fallback guard must live OUTSIDE the page loop —
    otherwise a multi-page bill whose first page is full-format would skip the
    simple-format fallback on later pages and silently drop their transactions.
    """
    items: list[TransactionItem] = []
    # Phase 1: full format across all pages.
    for page in pages:
        raw_text = page.extract_text() or ""
        text = _crop_transaction_section(raw_text)
        for match in _RE_TRANSACTION_LINE.finditer(text):
            item = _parse_text_transaction(match, billing_year, billing_month_num)
            if item is not None:
                items.append(item)

    # Phase 2: simple-format fallback only when full format found nothing.
    if not items:
        for page in pages:
            raw_text = page.extract_text() or ""
            text = _crop_transaction_section(raw_text)
            for match in _RE_TRANSACTION_LINE_SIMPLE.finditer(text):
                item = _parse_simple_text_transaction(
                    match, billing_year, billing_month_num
                )
                if item is not None:
                    items.append(item)
    return items


def _parse_text_transaction(
    match: re.Match[str],
    billing_year: int,
    billing_month_num: int = 0,
) -> TransactionItem | None:
    """Parse a full-format text transaction line."""
    try:
        trans_date = _parse_date(match.group(1), billing_year, billing_month_num)
        posting_date = _parse_date(match.group(2), billing_year, billing_month_num)
        merchant = match.group(3).strip()
        amount = int(match.group(4).replace(",", ""))

        if trans_date is None:
            return None

        # 退款商戶（退款/退費/退貨/沖銷…）保留為負數明細，利於對帳。
        if is_refund_merchant(merchant):
            amount = -abs(amount)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
            posting_date=posting_date,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", match.group(0))
        return None


def _parse_simple_text_transaction(
    match: re.Match[str],
    billing_year: int,
    billing_month_num: int = 0,
) -> TransactionItem | None:
    """Parse a simple-format text transaction line."""
    try:
        trans_date = _parse_date(match.group(1), billing_year, billing_month_num)
        merchant = match.group(2).strip()
        amount = int(match.group(3).replace(",", ""))

        if trans_date is None:
            return None

        # 退款商戶保留為負數明細，與其他路徑一致。
        if is_refund_merchant(merchant):
            amount = -abs(amount)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", match.group(0))
        return None


# Module-level registration
registry.register(CathayV1Parser())
