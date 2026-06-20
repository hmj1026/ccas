"""玉山銀行 (E.SUN) v1 信用卡帳單 parser。

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

# ESUN PDFs may not contain "玉山銀行" on page 0 — only in later pages.
# The distinctive marker is "玉山" + "信用卡帳單" anywhere in the document.
_ESUN_KEYWORDS = ("玉山", "信用卡帳單")

# -- Summary extraction patterns --

# 帳單月份：2026年03月 or 2026/03
_RE_BILLING_MONTH = re.compile(r"(\d{4})\s*[年/]\s*(\d{1,2})\s*月?\s*(?:份|月)")
# Real ESUN format: 這是您 115年02月 信用卡帳單 (ROC year)
_RE_ESUN_REAL_BILLING = re.compile(
    r"這是您\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*信用卡帳單"
)
# 繳費截止日：2026/04/15 or 繳款截止日：2026-04-15
_RE_DUE_DATE = re.compile(r"繳[費款]截止日[：:]\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
# Real ESUN format: "115/04/07 7.88%" (ROC year date followed by interest rate).
# Use percent-rate as anchor to avoid matching unrelated dates.
_RE_ESUN_REAL_DUE_DATE = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})\s+\d+\.\d+\s*%")
# Prefer "本期應繳總金額： TWD 26,920" on later pages (real format). The
# first-pass regex is strict to avoid matching "本期最低應繳金額" header rows.
_RE_TOTAL_AMOUNT_REAL = re.compile(r"本期應繳總金額[：:]?\s*(?:NT\$?|TWD)\s*([\d,]+)")
# Fallback: legacy synthetic formats like "本期應繳總額：NT$ 12,345".
_RE_TOTAL_AMOUNT = re.compile(
    r"(?:本期)?應繳(?:總金額|總額|金額)[：:]?\s*(?:NT\$?|TWD)?\s*([\d,]+)"
)

# -- ROC date support --

_ROC_OFFSET = 1911
_RE_ROC_DUE_DATE = re.compile(
    r"繳[費款]截止日[：:]\s*(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})"
)
_RE_ROC_BILLING_MONTH = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月")

# -- Transaction patterns --

_TRANSACTION_HEADER_KEYWORDS = ("交易日", "金額")
_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")

# Real ESUN format: MM/DD MM/DD MERCHANT TWD AMOUNT
_RE_ESUN_TXN_LINE = re.compile(
    r"^(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})\s+"
    r"(.+?)\s+TWD\s+(-?[\d,]+)\s*$",
    re.MULTILINE,
)
# Single-date refund/payment row (e.g. "03/09 感謝您辦理本行自動轉帳繳款！ TWD -10,615")
_RE_ESUN_TXN_SINGLE_DATE = re.compile(
    r"^(\d{1,2}/\d{1,2})\s+(.+?)\s+TWD\s+(-?[\d,]+)\s*$",
    re.MULTILINE,
)

# Text line-based transactions:
# YYYY/MM/DD  YYYY/MM/DD  MERCHANT  AMOUNT
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

    When billing_month_num is provided and the parsed month exceeds it, the year
    is shifted back by one to handle cross-year billing cycles.
    """
    parts = raw.split("/")
    if len(parts) != 3 and len(parts) != 2:
        return None

    try:
        if len(parts) == 2:
            mm = int(parts[0])
            cross_year = billing_month_num > 0 and mm > billing_month_num
            year = billing_year - 1 if cross_year else billing_year
            return date(year, mm, int(parts[1]))
        year_part = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        if year_part < 200:
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


class EsunV1Parser(BankParser):
    """玉山銀行信用卡帳單 v1 parser。"""

    bank_code = "ESUN"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is an E.SUN credit card statement.

        Scans all pages because some ESUN bills only mention "玉山銀行" on
        later pages (e.g. in the account-debit footer on page 3).
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False
                full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                return self._identify(full_text)
        except Exception:
            logger.debug("無法開啟 PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse E.SUN statement PDF into structured result."""
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
        """Check if first-page text contains E.SUN statement markers."""
        return all(kw in text for kw in _ESUN_KEYWORDS)

    def _extract_summary(
        self, pages: list[pdfplumber.page.Page]
    ) -> tuple[str, int, date]:
        """Extract billing_month, total_amount, due_date from page text.

        Raises:
            ParseError: If any mandatory summary field is missing.
        """
        full_text = "\n".join(page.extract_text() or "" for page in pages)

        # Zero-balance historical bills have no due date or amount and are
        # marked with "無需繳款". Skip as not-an-error.
        if "無需繳款" in full_text:
            raise ParseError(
                "zero-balance historical bill",
                reason="ESUN 無消費帳單無 due_date 與金額，略過",
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
        # Prefer real-format ROC year pattern anchored on "信用卡帳單".
        match = _RE_ESUN_REAL_BILLING.search(text)
        if match:
            roc_year = int(match.group(1))
            if roc_year < 200:
                ad_year = roc_year + _ROC_OFFSET
                return f"{ad_year}-{int(match.group(2)):02d}"
        match = _RE_BILLING_MONTH.search(text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}"
        match = _RE_ROC_BILLING_MONTH.search(text)
        if match:
            roc_year = int(match.group(1))
            month = int(match.group(2))
            ad_year = roc_year + _ROC_OFFSET
            return f"{ad_year}-{month:02d}"
        return None

    def _extract_due_date(self, text: str) -> date | None:
        """Extract due date from text."""
        match = _RE_DUE_DATE.search(text)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        match = _RE_ROC_DUE_DATE.search(text)
        if match:
            roc_year = int(match.group(1))
            if roc_year < 200:
                return date(
                    roc_year + _ROC_OFFSET,
                    int(match.group(2)),
                    int(match.group(3)),
                )
        # Real ESUN page-0 format: "115/04/07 7.88%" with no label; anchor on
        # the percent-rate to avoid matching unrelated dates.
        match = _RE_ESUN_REAL_DUE_DATE.search(text)
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
        """Extract total payable amount from text."""
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
    """Return True if the table header contains transaction keywords."""
    if not table:
        return False
    header = [str(cell or "") for cell in table[0]]
    header_text = " ".join(header)
    return all(kw in header_text for kw in _TRANSACTION_HEADER_KEYWORDS)


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

    Tries the real ESUN MM/DD + TWD format first, then falls back to the
    older full-date patterns for synthetic/test fixtures.
    """
    items: list[TransactionItem] = []
    for page in pages:
        text = page.extract_text() or ""
        page_spans: list[tuple[int, int]] = []
        for match in _RE_ESUN_TXN_LINE.finditer(text):
            item = _parse_esun_real_transaction(match, billing_year, billing_month_num)
            if item is not None:
                items.append(item)
                page_spans.append(match.span())
        # Single-date rows (refunds, payments) — skip text already captured
        # by the two-date pattern to avoid double-counting.
        for match in _RE_ESUN_TXN_SINGLE_DATE.finditer(text):
            if any(s <= match.start() < e for s, e in page_spans):
                continue
            item = _parse_esun_single_date_transaction(
                match, billing_year, billing_month_num
            )
            if item is not None:
                items.append(item)
    if items:
        return items

    # Legacy text fallback. Full format across all pages first; the simple-format
    # guard must sit OUTSIDE the page loop so a multi-page bill does not skip the
    # fallback on later pages once an earlier page matched full format.
    for page in pages:
        text = page.extract_text() or ""
        for match in _RE_TRANSACTION_LINE.finditer(text):
            item = _parse_text_transaction(match, billing_year, billing_month_num)
            if item is not None:
                items.append(item)

    if not items:
        for page in pages:
            text = page.extract_text() or ""
            for match in _RE_TRANSACTION_LINE_SIMPLE.finditer(text):
                item = _parse_simple_text_transaction(
                    match, billing_year, billing_month_num
                )
                if item is not None:
                    items.append(item)
    return items


def _parse_mmdd_loose(
    raw: str, billing_year: int, billing_month_num: int = 0
) -> date | None:
    """Parse MM/DD or M/D into a date (tolerant of 1-digit components)."""
    parts = raw.split("/")
    if len(parts) != 2:
        return None
    try:
        mm = int(parts[0])
        cross_year = billing_month_num > 0 and mm > billing_month_num
        year = billing_year - 1 if cross_year else billing_year
        return date(year, mm, int(parts[1]))
    except ValueError:
        return None


def _parse_esun_real_transaction(
    match: re.Match[str],
    billing_year: int,
    billing_month_num: int = 0,
) -> TransactionItem | None:
    """Parse a real-ESUN MM/DD + TWD transaction line."""
    try:
        trans_date = _parse_mmdd_loose(match.group(1), billing_year, billing_month_num)
        posting_date = _parse_mmdd_loose(
            match.group(2), billing_year, billing_month_num
        )
        merchant = match.group(3).strip()
        amount = parse_amount_cell(match.group(4))

        if trans_date is None:
            logger.warning("跳過日期無法解析的 ESUN 交易行: %s", match.group(0))
            return None

        # Skip rows that are summary/subtotal lines rather than real txns.
        if "本期" in merchant or "上期" in merchant or "合計" in merchant:
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
        logger.warning("跳過無法解析的 ESUN 交易行: %s", match.group(0))
        return None


def _parse_esun_single_date_transaction(
    match: re.Match[str],
    billing_year: int,
    billing_month_num: int = 0,
) -> TransactionItem | None:
    """Parse a single-date ESUN refund/payment line."""
    try:
        trans_date = _parse_mmdd_loose(match.group(1), billing_year, billing_month_num)
        merchant = match.group(2).strip()
        amount = parse_amount_cell(match.group(3))

        if trans_date is None:
            logger.warning("跳過日期無法解析的 ESUN 單日期交易行: %s", match.group(0))
            return None

        # Skip summary rows: "上期應繳金額： TWD 10,615" etc.
        if "應繳" in merchant or "合計" in merchant:
            return None

        # 退款/沖銷等貸方明細保留為負數明細。
        if is_refund_merchant(merchant):
            amount = -abs(amount)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的 ESUN 單日期交易行: %s", match.group(0))
        return None


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
        amount = parse_amount_cell(match.group(4))

        if trans_date is None:
            return None

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
        amount = parse_amount_cell(match.group(3))

        if trans_date is None:
            return None

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
registry.register(EsunV1Parser())
