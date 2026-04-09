"""Union Bank of Taiwan (UBOT) v1 credit card statement parser.

Uses pdfplumber to parse statement PDFs, extracting billing summary
and transaction details. Supports Western date format (YYYY/MM/DD)
with ROC calendar fallback.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pdfplumber
import pdfplumber.page
from pdfplumber.utils.exceptions import PdfminerException

from ccas.parser.base import BankParser, ParseError
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

_UBOT_KEYWORDS = ("聯邦銀行", "信用卡")

# -- Summary extraction patterns --

# Billing month: 2026年03月 or 2026/03
_RE_BILLING_MONTH = re.compile(r"(\d{4})\s*[年/]\s*(\d{1,2})\s*月?\s*(?:份|月)")
# Due date: 繳費截止日：2026/04/15 or 繳款截止日：2026-04-15
_RE_DUE_DATE = re.compile(r"繳[費款]截止日[：:]\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
# Total amount: 本期應繳總額：NT$ 12,345
_RE_TOTAL_AMOUNT = re.compile(
    r"(?:本期)?應繳[總金][額額][：:]?\s*(?:NT\$?\s*)?([\d,]+)"
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

_RE_TRANSACTION_LINE = re.compile(
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # trans_date
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # posting_date
    r"(.+?)\s+"  # merchant
    r"([\d,]+)\s*$",  # amount
    re.MULTILINE,
)

_RE_TRANSACTION_LINE_SIMPLE = re.compile(
    r"(\d{2,4}/\d{1,2}/\d{1,2})\s+"  # trans_date
    r"(.+?)\s+"  # merchant
    r"([\d,]+)\s*$",  # amount
    re.MULTILINE,
)


def _parse_date(raw: str, billing_year: int) -> date | None:
    """Parse a date string in various formats (YYYY/MM/DD, MM/DD, ROC YYY/MM/DD)."""
    parts = raw.split("/")
    if len(parts) != 3 and len(parts) != 2:
        return None

    try:
        if len(parts) == 2:
            return date(billing_year, int(parts[0]), int(parts[1]))
        year_part = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        if year_part < 200:
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


class UbotV1Parser(BankParser):
    """Union Bank of Taiwan credit card statement v1 parser."""

    bank_code = "UBOT"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is a UBOT credit card statement."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False
                text = pdf.pages[0].extract_text() or ""
                return self._identify(text)
        except (OSError, PdfminerException):
            logger.debug("Cannot open PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse UBOT statement PDF into structured result."""
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
        """Check if first-page text contains UBOT statement markers."""
        return all(kw in text for kw in _UBOT_KEYWORDS)

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
        return None

    def _extract_total_amount(self, text: str) -> int | None:
        """Extract total payable amount from text."""
        match = _RE_TOTAL_AMOUNT.search(text)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

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
    """Return True if the table header contains transaction keywords."""
    if not table:
        return False
    header = [str(cell or "") for cell in table[0]]
    header_text = " ".join(header)
    return all(kw in header_text for kw in _TRANSACTION_HEADER_KEYWORDS)


def _parse_transaction_row(
    row: list[str | None],
    year: int,
) -> TransactionItem | None:
    """Parse a single table row into a TransactionItem.

    Expected columns: [trans_date (MM/DD), posting_date (MM/DD), card_last4,
    merchant, amount]. Falls back to [trans_date, merchant, amount] for
    3-column tables.
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
                logger.warning("Skipping row with unparseable trans_date: %s", cells)
                return None

            amount = int(raw_amount.replace(",", ""))
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
            raw_trans_date = cells[0]
            merchant = cells[1]
            raw_amount = cells[2]

            trans_date = _parse_mmdd(raw_trans_date, year)
            if trans_date is None:
                trans_date = _parse_date(raw_trans_date, year)
            if trans_date is None:
                logger.warning("Skipping row with unparseable trans_date: %s", cells)
                return None

            amount = int(raw_amount.replace(",", ""))
            return TransactionItem(
                trans_date=trans_date,
                merchant=merchant,
                amount=amount,
            )

        logger.warning("Skipping row with insufficient columns: %s", cells)
        return None
    except (ValueError, IndexError):
        logger.warning("Skipping unparseable transaction row: %s", row)
        return None


# -- Text line extraction helpers --


def _extract_transactions_text(
    pages: list[pdfplumber.page.Page],
    billing_year: int,
) -> list[TransactionItem]:
    """Extract transactions from text lines.

    Tries full format (date date merchant amount) across all pages first,
    then falls back to simple format (date merchant amount) if none found.
    """
    items: list[TransactionItem] = []
    for page in pages:
        text = page.extract_text() or ""
        for match in _RE_TRANSACTION_LINE.finditer(text):
            item = _parse_text_transaction(match, billing_year)
            if item is not None:
                items.append(item)

    if not items:
        for page in pages:
            text = page.extract_text() or ""
            for match in _RE_TRANSACTION_LINE_SIMPLE.finditer(text):
                item = _parse_simple_text_transaction(match, billing_year)
                if item is not None:
                    items.append(item)
    return items


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

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
            posting_date=posting_date,
        )
    except (ValueError, IndexError):
        logger.warning("Skipping unparseable transaction line: %s", match.group(0))
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

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
        )
    except (ValueError, IndexError):
        logger.warning("Skipping unparseable transaction line: %s", match.group(0))
        return None


# Module-level registration
registry.register(UbotV1Parser())
