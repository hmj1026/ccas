"""台北富邦銀行 (Taipei Fubon Bank) v1 信用卡帳單 parser。

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
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

_FUBON_KEYWORDS = ("台北富邦", "信用卡")

# -- Summary extraction patterns --

# 帳單月份：2026年03月 or 帳單月份：2026/03
_RE_BILLING_MONTH = re.compile(r"(\d{4})\s*[年/]\s*(\d{1,2})\s*月?\s*(?:份|月)")
# 繳費截止日：2026/04/15 or 繳款截止日：2026-04-15 or 繳款期限 2026/04/15
_RE_DUE_DATE = re.compile(
    r"(?:繳[費款]截止日|繳款期限)[：:]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})"
)
# 本期應繳總額：NT$ 12,345 or 應繳金額 12,345
_RE_TOTAL_AMOUNT = re.compile(
    r"(?:本期)?應繳[總金][額額][：:]?\s*(?:NT\$?\s*)?([\d,]+)"
)

# -- ROC date support --

_ROC_OFFSET = 1911
_RE_ROC_DUE_DATE = re.compile(
    r"(?:繳[費款]截止日|繳款期限)[：:]?\s*(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})"
)
_RE_ROC_BILLING_MONTH = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月")

# Tabular header format (real FUBON PDFs):
# 帳單年月 ... 繳款截止日 ...
# 115/04   ... 115/04/24  ...
_RE_FUBON_BILLING_MONTH = re.compile(r"帳單年月.*\n\s*(\d{2,3})/(\d{1,2})")
_RE_FUBON_DUE_DATE = re.compile(
    r"繳款截止日.*\n"
    r".*?(\d{2,3})/(\d{1,2})/(\d{1,2})\s+"
    r"(\d{2,3})/(\d{1,2})/(\d{1,2})"
)

# -- Transaction patterns --

# Card header: "MASTER鈦金正卡末４碼5273" or "VISA白金卡末4碼1234"
_RE_CARD_HEADER = re.compile(r"末[４4]碼(\d{4})")

# Installment suffix in merchant: "(01/06期)" or "(1/6期)"
_RE_INSTALLMENT = re.compile(r"\s*\((\d{1,2})/(\d{1,2})期\)\s*$")

# Table-based: headers contain 交易日 and 金額
_TRANSACTION_HEADER_KEYWORDS = ("交易日", "金額")
_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")

# Text line-based transactions:
# MM/DD  MM/DD  MERCHANT  AMOUNT  (full format with posting date)
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

# Real FUBON format: ROC_DATE MERCHANT ROC_DATE [TWD] AMOUNT
_RE_FUBON_TRANSACTION_LINE = re.compile(
    r"(\d{2,3}/\d{1,2}/\d{1,2})\s+"  # trans_date (ROC)
    r"(.+?)\s+"  # merchant
    r"(\d{2,3}/\d{1,2}/\d{1,2})\s+"  # posting_date (ROC)
    r"(?:TWD\s+)?"  # optional currency
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


def _extract_installment(
    merchant: str,
) -> tuple[str, int | None, int | None]:
    """Extract installment info from merchant and return cleaned merchant."""
    match = _RE_INSTALLMENT.search(merchant)
    if not match:
        return merchant, None, None
    cleaned = merchant[: match.start()].strip()
    return cleaned, int(match.group(1)), int(match.group(2))


class FubonV1Parser(BankParser):
    """台北富邦銀行信用卡帳單 v1 parser。"""

    bank_code = "FUBON"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PDF is a Taipei Fubon Bank credit card statement.

        Scans the first 2 pages because some FUBON statements omit
        '信用卡' from page 1 (only showing it in the transaction detail
        section on page 2+).
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False
                text = "\n".join(p.extract_text() or "" for p in pdf.pages[:2])
                return self._identify(text)
        except Exception:
            logger.debug("無法開啟 PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse Taipei Fubon Bank statement PDF into structured result."""
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
        """Check if first-page text contains Taipei Fubon Bank statement markers."""
        return all(kw in text for kw in _FUBON_KEYWORDS)

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
        # Try FUBON tabular header (most specific, avoids disclaimer false positives)
        match = _RE_FUBON_BILLING_MONTH.search(text)
        if match:
            roc_year = int(match.group(1))
            month = int(match.group(2))
            return f"{roc_year + _ROC_OFFSET}-{month:02d}"
        # Try generic ROC year
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
        # Try ROC date with label
        match = _RE_ROC_DUE_DATE.search(text)
        if match:
            roc_year = int(match.group(1))
            if roc_year < 200:
                return date(
                    roc_year + _ROC_OFFSET,
                    int(match.group(2)),
                    int(match.group(3)),
                )
        # Try FUBON tabular: 帳單結帳日 + 繳款截止日 on header, dates on data row
        match = _RE_FUBON_DUE_DATE.search(text)
        if match:
            roc_year = int(match.group(4))
            if roc_year < 200:
                return date(
                    roc_year + _ROC_OFFSET,
                    int(match.group(5)),
                    int(match.group(6)),
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

    Tries FUBON format (date merchant date [TWD] amount) first,
    then full format (date date merchant amount),
    then simple format (date merchant amount).

    Tracks card_last4 from card header lines (e.g. "末４碼5273").
    """
    items: list[TransactionItem] = []
    current_card: str | None = None
    for page in pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            card_match = _RE_CARD_HEADER.search(line)
            if card_match:
                current_card = card_match.group(1)
                continue
            txn_match = _RE_FUBON_TRANSACTION_LINE.match(line.strip())
            if txn_match:
                item = _parse_fubon_text_transaction(
                    txn_match, billing_year, card_last4=current_card,
                )
                if item is not None:
                    items.append(item)

    if not items:
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


def _parse_fubon_text_transaction(
    match: re.Match[str],
    billing_year: int,
    *,
    card_last4: str | None = None,
) -> TransactionItem | None:
    """Parse a FUBON-format text transaction: DATE MERCHANT DATE [TWD] AMOUNT."""
    try:
        trans_date = _parse_date(match.group(1), billing_year)
        raw_merchant = match.group(2).strip()
        posting_date = _parse_date(match.group(3), billing_year)
        amount = int(match.group(4).replace(",", ""))

        if trans_date is None:
            return None

        merchant, inst_cur, inst_tot = _extract_installment(raw_merchant)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
            posting_date=posting_date,
            card_last4=card_last4,
            installment_current=inst_cur,
            installment_total=inst_tot,
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

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant,
            amount=amount,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", match.group(0))
        return None


# Module-level registration
registry.register(FubonV1Parser())
