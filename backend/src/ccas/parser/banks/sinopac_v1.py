"""永豐銀行 (SinoPac) v1 信用卡帳單 parser。

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
from ccas.parser.refund_utils import REFUND_LINE_PREFIXES, is_refund_merchant
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

_SINOPAC_KEYWORDS = ("永豐銀行", "信用卡")

# -- Summary extraction patterns --

# 帳單月份：2026年03月 or 帳單月份：2026/03
_RE_BILLING_MONTH = re.compile(r"(\d{4})\s*[年/]\s*(\d{1,2})\s*月?\s*(?:份|月)")
# 繳費截止日：2026/04/15 or 繳款截止日 2026-04-15 (colon optional — real
# SINOPAC PDFs omit it, e.g. "您的繳款截止日2026/03/27").
_RE_DUE_DATE = re.compile(r"繳[費款]截止日[：:]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
# 本期應繳總額：NT$ 12,345 or 本期應繳金額 12,345 or 應繳總額：12,345
_RE_TOTAL_AMOUNT = re.compile(
    r"(?:本期)?應繳[總金][額額][：:]?\s*(?:NT\$?\s*)?([\d,]+)"
)
# Real-PDF summary row: "臺幣 上期 已繳 新增 循環 違約 本期應繳 最低" — 7 numeric
# columns following the 臺幣 literal, with the 6th being 本期應繳總金額 (index 5).
_RE_SUMMARY_ROW = re.compile(
    r"臺幣\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)"
)
# Zero-balance historical bills carry this marker and have no due date / amount.
_ZERO_BALANCE_MARKER = "無需繳款"

# -- ROC date support --

_ROC_OFFSET = 1911
_RE_ROC_DUE_DATE = re.compile(
    r"繳[費款]截止日[：:]\s*(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})"
)
_RE_ROC_BILLING_MONTH = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月")

# -- Transaction patterns --

# Table-based: real SINOPAC table headers contain 入帳 and 臺幣金額 (the legacy
# synthetic fixture used 交易日/金額, which we also keep for back-compat).
_TRANSACTION_HEADER_KEYWORDS_LEGACY = ("交易日", "金額")
_TRANSACTION_HEADER_KEYWORDS_REAL = ("入帳", "臺幣金額")
_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")

# Real-PDF transaction line: MM/DD MM/DD [optional 4-digit card] merchant amount
# e.g. "02/18 02/24 4300 悠遊卡自動加值─台北捷 500"
#      "03/05 03/05 永豐自扣已入帳，謝謝！ -7,147"
_RE_SINOPAC_REAL_TXN = re.compile(
    r"^(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})\s+"
    r"(?:(\d{4})\s+)?"  # optional card_last4
    r"(.+?)\s+(-?[\d,]+)\s*$",
    re.MULTILINE,
)

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

# 永豐自扣（自動扣款入帳）為永豐專屬措辭，以 extra_keywords 補充至共用退款判定。
_SINOPAC_EXTRA_REFUND_KEYWORDS = ("永豐自扣",)


def _is_refund_row(raw_line: str, merchant: str, amount: int) -> bool:
    """Return True if the row represents a refund / credit / auto-debit.

    Delegates merchant-keyword matching to the shared ``is_refund_merchant``
    (which uses ``startswith`` so legitimate merchants containing a keyword
    mid-word — e.g. 「退休俱樂部」 — are not filtered), and additionally treats
    negative amounts and ``(-)``-prefixed lines as refunds.
    """
    if is_refund_merchant(merchant, extra_keywords=_SINOPAC_EXTRA_REFUND_KEYWORDS):
        return True
    if amount < 0:
        return True
    if raw_line.lstrip().startswith(REFUND_LINE_PREFIXES):
        return True
    return False


def _parse_date(raw: str, billing_year: int) -> date | None:
    """Parse a date string in various formats (YYYY/MM/DD, MM/DD, ROC YYY/MM/DD)."""
    parts = raw.split("/")
    if len(parts) != 3 and len(parts) != 2:
        return None

    try:
        if len(parts) == 2:
            # MM/DD format
            return date(billing_year, int(parts[0]), int(parts[1]))
        year_part = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        if year_part < 200:
            # ROC year
            year_part += _ROC_OFFSET
        return date(year_part, month, day)
    except (ValueError, IndexError):
        return None


def _parse_mmdd(raw: str, year: int) -> date | None:
    """Parse an 'MM/DD' string into a Python date using the given year."""
    match = _RE_DATE_MMDD.match(raw)
    if not match:
        return None
    return date(year, int(match.group(1)), int(match.group(2)))


class SinopacV1Parser(BankParser):
    """永豐銀行信用卡帳單 v1 parser。"""

    bank_code = "SINOPAC"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is a SinoPac credit card statement."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False
                text = pdf.pages[0].extract_text() or ""
                return self._identify(text)
        except Exception:
            logger.debug("無法開啟 PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse SinoPac statement PDF into structured result."""
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages
            billing_month, total_amount, due_date = self._extract_summary(pages)
            billing_year = int(billing_month.split("-")[0])
            transactions = self._extract_transactions(pages, billing_year)

        return ParseResult(
            bank_code=self.bank_code,
            billing_month=billing_month,
            total_amount=total_amount,
            due_date=due_date,
            transactions=transactions,
        )

    def _identify(self, text: str) -> bool:
        """Check if first-page text contains SinoPac statement markers."""
        return all(kw in text for kw in _SINOPAC_KEYWORDS)

    def _extract_summary(
        self, pages: list[pdfplumber.page.Page]
    ) -> tuple[str, int, date]:
        """Extract billing_month, total_amount, due_date from page text.

        Raises:
            ParseError: If any mandatory summary field is missing, or with
                reason ``"zero-balance historical bill"`` when the statement
                is an old no-activity bill that intentionally omits due date
                and amount.
        """
        full_text = "\n".join(page.extract_text() or "" for page in pages)

        if _ZERO_BALANCE_MARKER in full_text:
            raise ParseError(
                "zero-balance historical bill",
                reason="SINOPAC 無消費帳單無 due_date 與金額，略過",
            )

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
        # Try ROC year
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
        # Try ROC date
        match = _RE_ROC_DUE_DATE.search(text)
        if match:
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

        Real SINOPAC bills list amounts in a summary row beginning with
        ``臺幣`` followed by seven numbers (上期/已繳/新增/循環/違約/本期應繳/最低);
        the 6th (index 5) is 本期應繳總金額. Older synthetic fixtures use the
        keyword style ``本期應繳總額：NT$ 12,345`` which we keep as fallback.
        """
        row_match = _RE_SUMMARY_ROW.search(text)
        if row_match:
            return int(row_match.group(6).replace(",", ""))

        keyword_match = _RE_TOTAL_AMOUNT.search(text)
        if keyword_match:
            return int(keyword_match.group(1).replace(",", ""))
        return None

    def _extract_transactions(
        self,
        pages: list[pdfplumber.page.Page],
        billing_year: int,
    ) -> tuple[TransactionItem, ...]:
        """Extract transaction items from all pages.

        Tries table extraction first, then text line parsing.
        """
        items = _extract_transactions_table(pages, billing_year)
        if items:
            return tuple(items)

        items = _extract_transactions_text(pages, billing_year)
        return tuple(items)


# -- Table extraction helpers --


def _extract_transactions_table(
    pages: list[pdfplumber.page.Page],
    billing_year: int,
) -> list[TransactionItem]:
    """Extract transactions from tables."""
    items: list[TransactionItem] = []
    for page in pages:
        for table in page.extract_tables():
            if not _is_transaction_table(table):
                continue
            for row in table[1:]:
                item = _parse_transaction_row(row, billing_year)
                if item is not None:
                    items.append(item)
    return items


def _is_transaction_table(table: list[list[str | None]]) -> bool:
    """Return True if the table header contains transaction keywords.

    Accepts either the legacy synthetic header (``交易日 / 金額``) used by
    historical unit fixtures, or the real-PDF header (``入帳 / 臺幣金額``).
    """
    if not table:
        return False
    header = [str(cell or "") for cell in table[0]]
    header_text = " ".join(header)
    if all(kw in header_text for kw in _TRANSACTION_HEADER_KEYWORDS_LEGACY):
        return True
    return all(kw in header_text for kw in _TRANSACTION_HEADER_KEYWORDS_REAL)


def _parse_transaction_row(
    row: list[str | None],
    year: int,
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

            trans_date = _parse_mmdd(raw_trans_date, year)
            if trans_date is None:
                trans_date = _parse_date(raw_trans_date, year)
            if trans_date is None:
                logger.warning("跳過無法解析交易日的行: %s", cells)
                return None

            amount = int(raw_amount.replace(",", ""))
            # 與文字路徑一致：退款保留為負數（R14 / R26）。table cell 無原始
            # 行文字，故 raw_line 傳空字串（僅靠 merchant 關鍵字與負號判定）。
            if _is_refund_row("", merchant, amount):
                amount = -abs(amount)
            posting_date = _parse_mmdd(raw_posting_date, year)
            if posting_date is None:
                posting_date = _parse_date(raw_posting_date, year)
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

            trans_date = _parse_mmdd(raw_trans_date, year)
            if trans_date is None:
                trans_date = _parse_date(raw_trans_date, year)
            if trans_date is None:
                logger.warning("跳過無法解析交易日的行: %s", cells)
                return None

            amount = int(raw_amount.replace(",", ""))
            if _is_refund_row("", merchant, amount):
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
) -> list[TransactionItem]:
    """Extract transactions from text lines.

    Tries the real-PDF MM/DD format first (covers all production SINOPAC
    bills), then falls back to legacy YYYY/MM/DD patterns for back-compat
    with older fixtures.
    """
    # Three fallback tiers for mutually-exclusive PDF formats. Each tier scans
    # ALL pages before the next tier's guard is evaluated — guards must live
    # outside the page loop, otherwise a multi-page bill that matched an earlier
    # tier on page 1 would silently skip later pages' rows.
    items: list[TransactionItem] = []

    # Tier 1: real-PDF MM/DD format (covers all production SINOPAC bills).
    for page in pages:
        text = page.extract_text() or ""
        for match in _RE_SINOPAC_REAL_TXN.finditer(text):
            item = _parse_real_text_transaction(match, billing_year)
            if item is not None:
                items.append(item)

    # Tier 2: legacy full format (date date merchant amount).
    if not items:
        for page in pages:
            text = page.extract_text() or ""
            for match in _RE_TRANSACTION_LINE.finditer(text):
                item = _parse_text_transaction(match, billing_year)
                if item is not None:
                    items.append(item)

    # Tier 3: legacy simple format (date merchant amount).
    if not items:
        for page in pages:
            text = page.extract_text() or ""
            for match in _RE_TRANSACTION_LINE_SIMPLE.finditer(text):
                item = _parse_simple_text_transaction(match, billing_year)
                if item is not None:
                    items.append(item)
    return items


def _parse_real_text_transaction(
    match: re.Match[str],
    billing_year: int,
) -> TransactionItem | None:
    """Parse a real SINOPAC MM/DD formatted text transaction line."""
    try:
        trans_date = _parse_mmdd(match.group(1), billing_year)
        posting_date = _parse_mmdd(match.group(2), billing_year)
        card_last4 = match.group(3)
        merchant = match.group(4).strip()
        amount = int(match.group(5).replace(",", ""))

        if trans_date is None:
            return None

        # Skip summary/totals rows like "您的正卡，本期應繳金額合計 12,579"
        if "本期應繳金額合計" in merchant or "小計" in merchant:
            return None

        # 退款 / 回饋 / 沖銷：保留為負數明細（利於對帳），而非整筆丟棄（R26）。
        if _is_refund_row(match.group(0), merchant, amount):
            amount = -abs(amount)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
            posting_date=posting_date,
            card_last4=card_last4,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", match.group(0))
        return None


def _parse_text_transaction(
    match: re.Match[str],
    billing_year: int,
) -> TransactionItem | None:
    """Parse a full-format text transaction line."""
    try:
        trans_date = _parse_date(match.group(1), billing_year)
        posting_date = _parse_date(match.group(2), billing_year)
        merchant = match.group(3).strip()
        amount = int(match.group(4).replace(",", ""))

        if trans_date is None:
            return None

        # 退款保留為負數，與 Tier-1 / table 路徑一致（R14 / R26）。
        if _is_refund_row(match.group(0), merchant, amount):
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
) -> TransactionItem | None:
    """Parse a simple-format text transaction line."""
    try:
        trans_date = _parse_date(match.group(1), billing_year)
        merchant = match.group(2).strip()
        amount = int(match.group(3).replace(",", ""))

        if trans_date is None:
            return None

        # 退款保留為負數，與其他路徑一致（R14 / R26）。
        if _is_refund_row(match.group(0), merchant, amount):
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
registry.register(SinopacV1Parser())
