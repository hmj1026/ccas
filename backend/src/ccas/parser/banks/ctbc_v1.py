"""中國信託 (CTBC) v1 信用卡帳單 parser。

使用 pdfplumber 解析表格式帳單 PDF，提取帳單摘要與交易明細。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pdfplumber
import pdfplumber.page

from ccas.parser.base import BankParser, ParseError
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

_CTBC_KEYWORDS = ("中國信託", "信用卡")

# -- Summary extraction patterns --

_RE_DUE_DATE = re.compile(r"繳費截止日[：:]\s*(\d{4})/(\d{2})/(\d{2})")
_RE_TOTAL_AMOUNT = re.compile(r"本期應繳總額[：:]\s*NT\$\s*([\d,]+)")
_RE_BILLING_MONTH = re.compile(r"帳單月份[：:]\s*(\d{4})年(\d{2})月")

# -- Transaction table patterns --

_TRANSACTION_HEADER_KEYWORDS = ("交易日", "金額")
_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")


class CtbcV1Parser(BankParser):
    """中國信託信用卡帳單 v1 parser。"""

    bank_code = "CTBC"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is a CTBC credit card statement."""
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
        """Parse CTBC statement PDF into structured result."""
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
        """Check if first-page text contains CTBC statement markers."""
        return all(kw in text for kw in _CTBC_KEYWORDS)

    def _extract_summary(
        self, pages: list[pdfplumber.page.Page]
    ) -> tuple[str, int, date]:
        """Extract billing_month, total_amount, due_date from page text.

        Raises:
            ParseError: If any mandatory summary field is missing.
        """
        full_text = "\n".join(page.extract_text() or "" for page in pages)

        due_match = _RE_DUE_DATE.search(full_text)
        if not due_match:
            raise ParseError("帳單摘要缺失", reason="找不到繳費截止日")
        due_date = date(
            int(due_match.group(1)),
            int(due_match.group(2)),
            int(due_match.group(3)),
        )

        total_match = _RE_TOTAL_AMOUNT.search(full_text)
        if not total_match:
            raise ParseError("帳單摘要缺失", reason="找不到應繳總額")
        total_amount = int(total_match.group(1).replace(",", ""))

        month_match = _RE_BILLING_MONTH.search(full_text)
        if not month_match:
            raise ParseError("帳單摘要缺失", reason="找不到帳單月份")
        billing_month = f"{month_match.group(1)}-{month_match.group(2)}"

        return billing_month, total_amount, due_date

    def _extract_transactions(
        self,
        pages: list[pdfplumber.page.Page],
        billing_year: int,
    ) -> tuple[TransactionItem, ...]:
        """Extract transaction items from all pages' tables.

        Skips malformed rows with a warning log instead of raising.
        """
        items: list[TransactionItem] = []

        for page in pages:
            for table in page.extract_tables():
                if not _is_transaction_table(table):
                    continue
                for row in table[1:]:
                    item = _parse_transaction_row(row, billing_year)
                    if item is not None:
                        items.append(item)

        return tuple(items)


def _is_transaction_table(table: list[list[str | None]]) -> bool:
    """Check if a table looks like a transaction table by header keywords."""
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

    Returns None (with warning log) if the row is malformed.
    """
    try:
        cells = [str(cell or "").strip() for cell in row]
        if len(cells) < 5:
            logger.warning("跳過欄位不足的交易行: %s", cells)
            return None

        raw_trans_date = cells[0]
        raw_posting_date = cells[1]
        raw_card_last4 = cells[2]
        merchant = cells[3]
        raw_amount = cells[4]

        trans_date = _parse_mmdd(raw_trans_date, year)
        if trans_date is None:
            logger.warning("跳過無法解析交易日的行: %s", cells)
            return None

        amount = int(raw_amount.replace(",", ""))

        posting_date = _parse_mmdd(raw_posting_date, year)
        is_valid_card = raw_card_last4.isdigit() and len(raw_card_last4) == 4
        card_last4 = raw_card_last4 if is_valid_card else None

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
            posting_date=posting_date,
            card_last4=card_last4,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", row)
        return None


def _parse_mmdd(raw: str, year: int) -> date | None:
    """Parse MM/DD string to date using the billing statement year."""
    match = _RE_DATE_MMDD.match(raw)
    if not match:
        return None
    return date(year, int(match.group(1)), int(match.group(2)))


# Module-level registration
registry.register(CtbcV1Parser())
