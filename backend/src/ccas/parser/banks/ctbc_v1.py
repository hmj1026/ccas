"""中國信託 (CTBC) v1 信用卡帳單 parser。

使用 pdfplumber 解析帳單 PDF，提取帳單摘要與交易明細。
支援兩種格式：
- 標籤式（合成測試 PDF）：中文標籤 + 西元年 + 表格式交易
- 民國年式（真實帳單 PDF）：ROC 年 + 文字行式交易
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

import pdfplumber
import pdfplumber.page

from ccas.parser.banks.ctbc.ocr_postprocess import normalize_ocr_merchant
from ccas.parser.base import BankParser, ParseError
from ccas.parser.ocr import extract_text_from_image, is_ocr_available
from ccas.parser.refund_utils import is_refund_merchant, parse_amount_cell
from ccas.parser.registry import registry
from ccas.parser.result import ParseResult, TransactionItem

logger = logging.getLogger(__name__)

# -- Identification patterns --

_CTBC_KEYWORDS = ("中國信託", "信用卡")
_CTBC_URL_MARKER = "ctbc.tw"

# -- Labeled format (synthetic test PDFs) --

_RE_DUE_DATE = re.compile(r"繳費截止日[：:]\s*(\d{4})/(\d{2})/(\d{2})")
_RE_TOTAL_AMOUNT = re.compile(r"本期應繳總額[：:]\s*NT\$\s*([\d,]+)")
_RE_BILLING_MONTH = re.compile(r"帳單月份[：:]\s*(\d{4})年(\d{2})月")
_TRANSACTION_HEADER_KEYWORDS = ("交易日", "金額")
_RE_DATE_MMDD = re.compile(r"^(\d{2})/(\d{2})$")

# -- ROC format (real CTBC PDFs) --

_ROC_OFFSET = 1911
_RE_BILLING_LINE_ROC = re.compile(r"^(\d{3})\s+(\d{2})\s+\d+\s*/\s*\d+", re.MULTILINE)
_RE_ROC_DATE = re.compile(r"(\d{3})/(\d{2})/(\d{2})")
_RE_DOLLAR_AMOUNT = re.compile(r"\$\s*([\d,]+)")
_RE_TRANSACTION_LINE_ROC = re.compile(
    r"(\d{3}/\d{2}/\d{2})\s+(\d{3}/\d{2}/\d{2})\s+([\d,]+)\s+(\d{4})\s+([A-Z]{2,4})"
)

# Garbled font detection: PDFs with embedded/non-unicode fonts produce (cid:N) tokens
_RE_CID = re.compile(r"\(cid:\d+\)")

# OCR legacy format (old CTBC PDFs, embedded fonts, 300-dpi OCR text)
_RE_BILLING_MONTH_OCR_LEGACY = re.compile(r"(\d{2,3})年\s*(\d{2})月")
_RE_DUE_DATE_OCR_LEGACY = re.compile(r"繳款截止日\s+(\d{3})/(\d{2})/(\d{2})")
_RE_TOTAL_AMOUNT_OCR_LEGACY = re.compile(r"本期應繳總金額\s+([\d,]+)")

# 2-page zero-balance bill: rate line "NNN/MM RATE" on page 1
_RE_PAGE1_RATE_LINE = re.compile(r"^\d{3}/\d{2}\s+([\d.]+)$", re.MULTILINE)
# ROC year+month only (no day), negative lookahead avoids matching full NNN/MM/DD dates
_RE_ROC_YEAR_MONTH = re.compile(r"\b(\d{3})/(\d{2})\b(?!/)")


def _is_garbled(text: str) -> bool:
    """Return True if text is predominantly CID-encoded garbage.

    More than 5 (cid:N) tokens indicates the PDF uses embedded fonts
    that pdfplumber cannot decode — OCR fallback is needed.
    """
    return len(_RE_CID.findall(text)) > 5


def _ocr_page_full(page: pdfplumber.page.Page) -> str:
    """OCR an entire page for identification / full-text extraction.

    Uses --psm 3 (auto page layout) at 300 dpi to handle older PDFs
    with embedded fonts whose text cannot be decoded by pdfplumber.
    Returns empty string if OCR is unavailable or fails.
    """
    if not is_ocr_available():
        return ""
    try:
        import pytesseract  # noqa: PLC0415

        pil_image = page.to_image(resolution=300).original
        return pytesseract.image_to_string(
            pil_image, lang="chi_tra", config="--psm 3"
        ).strip()
    except (RuntimeError, OSError, AttributeError):
        logger.debug("整頁 OCR 失敗（用於識別）", exc_info=True)
        return ""


# Known non-transaction text that OCR may extract from section headers.
# "帳單分期" intentionally covers all sub-variants (帳單分期入帳, etc.)
_NON_TRANSACTION_MERCHANTS: frozenset[str] = frozenset(
    {
        "消費暨收費摘要表",
        "帳單分期",
    }
)


def _is_non_transaction_merchant(merchant: str) -> bool:
    """Check if merchant text matches a known non-transaction header."""
    return any(keyword in merchant for keyword in _NON_TRANSACTION_MERCHANTS)


def _roc_to_date(roc_year: int, month: int, day: int) -> date:
    """Convert ROC (minguo) date to Python date."""
    return date(roc_year + _ROC_OFFSET, month, day)


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
                page = pdf.pages[0]
                text = page.extract_text() or ""
                if self._identify(text):
                    return True
                # Fallback: OCR page 1 for PDFs with garbled/embedded font encoding
                if is_ocr_available():
                    ocr_text = _ocr_page_full(page)
                    return self._identify(ocr_text)
                return False
        except Exception:
            logger.debug("無法開啟 PDF: %s", pdf_path, exc_info=True)
            return False

    def parse(self, pdf_path: Path) -> ParseResult:
        """Parse CTBC statement PDF into structured result."""
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages
            billing_month, total_amount, due_date, due_date_estimated = (
                self._extract_summary(pages)
            )
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
            due_date_estimated=due_date_estimated,
        )

    def _identify(self, text: str) -> bool:
        """Check if first-page text contains CTBC statement markers.

        Accepts any of:
        - All Chinese keywords (labeled/synthetic PDFs), OR
        - ROC billing month header (real PDFs, all years)

        The ROC header pattern ``NNN MM P / T`` (e.g. ``115 03 1 / 3``)
        is specific to CTBC statements and sufficient for identification.
        Older PDFs (ROC 106-110) lack the ctbc.tw URL present in newer ones.
        """
        has_keywords = all(kw in text for kw in _CTBC_KEYWORDS)
        has_roc_header = _RE_BILLING_LINE_ROC.search(text) is not None
        return has_keywords or has_roc_header

    def _extract_summary(
        self, pages: list[pdfplumber.page.Page]
    ) -> tuple[str, int, date, bool]:
        """Extract billing_month, total_amount, due_date, due_date_estimated.

        Tries ROC format first (real PDFs), then labeled format (test PDFs).
        ``due_date_estimated`` is ``True`` only when the due date had to be
        estimated via the page-1 day-28 fallback (CTBC 2-page bills lacking a
        precise cutoff); every other extraction path yields ``False``.

        Raises:
            ParseError: If any mandatory summary field is missing.
        """
        full_text = "\n".join(page.extract_text() or "" for page in pages)
        first_page_text = pages[0].extract_text() or ""
        last_page_text = pages[-1].extract_text() or ""

        # Fallback: if font encoding is garbled, re-extract all pages via OCR
        if _is_garbled(full_text):
            logger.info("偵測到亂碼字型，改用 OCR 全頁解析")
            full_text = "\n".join(_ocr_page_full(p) for p in pages)
            first_page_text = _ocr_page_full(pages[0]) if pages else ""
            last_page_text = _ocr_page_full(pages[-1]) if pages else ""

        billing_month = _extract_billing_month_roc(first_page_text)
        if billing_month is None:
            billing_month = _extract_billing_month_labeled(full_text)
        if billing_month is None:
            billing_month = _extract_billing_month_ocr_legacy(full_text)
        if billing_month is None:
            raise ParseError("帳單摘要缺失", reason="找不到帳單月份")

        due_date_estimated = False
        due_date = _extract_due_date_labeled(full_text)
        if due_date is None:
            due_date = _extract_due_date_ocr_legacy(full_text)
        if due_date is None:
            # _extract_due_date_roc is only reliable when the last page is a
            # payment slip (identified by the presence of a $AMOUNT marker).
            # For 2-page bills the last page is a transaction page — skip it.
            if _extract_total_amount_dollar(last_page_text) is not None:
                due_date = _extract_due_date_roc(last_page_text, billing_month)
        if due_date is None:
            page1_due = _extract_due_date_page1(first_page_text)
            if page1_due is not None:
                due_date, due_date_estimated = page1_due
        if due_date is None:
            raise ParseError("帳單摘要缺失", reason="找不到繳費截止日")

        total_amount = _extract_total_amount_labeled(full_text)
        if total_amount is None:
            total_amount = _extract_total_amount_ocr_legacy(full_text)
        if total_amount is None:
            total_amount = _extract_total_amount_dollar(last_page_text)
        if total_amount is None:
            total_amount = _extract_total_amount_page1(first_page_text)
        if total_amount is None:
            raise ParseError("帳單摘要缺失", reason="找不到應繳總額")

        return billing_month, total_amount, due_date, due_date_estimated

    def _extract_transactions(
        self,
        pages: list[pdfplumber.page.Page],
        billing_year: int,
        billing_month_num: int = 0,
    ) -> tuple[TransactionItem, ...]:
        """Extract transaction items from all pages.

        Tries table extraction first (labeled format), then
        text line parsing (ROC format). Skips malformed rows.

        ``billing_month_num`` (1-12) enables cross-year correction for the
        labeled MM/DD format: a January bill listing December transactions
        must roll the year back by one. ``0`` (default) disables the shift
        for backward compatibility. The ROC path uses full 民國年 dates and
        is unaffected.
        """
        items = _extract_transactions_table(pages, billing_year, billing_month_num)
        if items:
            return tuple(items)

        items = _extract_transactions_roc(pages)
        return tuple(items)


# -- Labeled format helpers (synthetic test PDFs) --


def _extract_billing_month_labeled(text: str) -> str | None:
    """Extract billing month from labeled format: '帳單月份：YYYY年MM月'.

    Args:
        text: Full PDF text from labeled/synthetic test PDFs.

    Returns:
        Billing month string in 'YYYY-MM' format, or None if not found.
    """
    match = _RE_BILLING_MONTH.search(text)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def _extract_due_date_labeled(text: str) -> date | None:
    """Extract due date from labeled format: '繳費截止日：YYYY/MM/DD'.

    Args:
        text: Full PDF text from labeled/synthetic test PDFs.

    Returns:
        Due date as a Python date, or None if not found.
    """
    match = _RE_DUE_DATE.search(text)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _extract_total_amount_labeled(text: str) -> int | None:
    """Extract total payable amount from labeled format: '本期應繳總額：NT$N,NNN'.

    Args:
        text: Full PDF text from labeled/synthetic test PDFs.

    Returns:
        Total amount as an integer (TWD), or None if not found.
    """
    match = _RE_TOTAL_AMOUNT.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_transactions_table(
    pages: list[pdfplumber.page.Page],
    billing_year: int,
    billing_month_num: int = 0,
) -> list[TransactionItem]:
    """Extract transactions from tables (labeled/test format)."""
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
    """Return True if the table header contains the expected transaction keywords.

    Checks that both '交易日' and '金額' appear in the joined header row text,
    distinguishing transaction tables from other tables in the PDF.

    Args:
        table: Raw table data extracted by pdfplumber, rows of optional strings.

    Returns:
        True if the table looks like a transaction detail table.
    """
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
    """Parse a single labeled-format table row into a TransactionItem.

    Expected columns: [trans_date (MM/DD), posting_date (MM/DD), card_last4,
    merchant, amount]. Rows with fewer than 5 columns or unparseable dates
    are skipped with a warning log.

    Args:
        row: Raw table row cells (may contain None).
        year: Calendar year to combine with MM/DD dates.
        billing_month_num: Billing month (1-12) for cross-year correction;
            ``0`` disables the shift.

    Returns:
        TransactionItem on success, or None if the row should be skipped.
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

        trans_date = _parse_mmdd(raw_trans_date, year, billing_month_num)
        if trans_date is None:
            logger.warning("跳過無法解析交易日的行: %s", cells)
            return None

        # 退款保留為負數明細（與 refund_policy 一致）：parse_amount_cell 先處理
        # 會計括號 / 負號編碼，再依商戶名是否為退款措辭強制負數（-abs 防重複負數化）。
        merchant_name = normalize_ocr_merchant(merchant)
        amount = parse_amount_cell(raw_amount)
        if is_refund_merchant(merchant_name):
            amount = -abs(amount)
        posting_date = _parse_mmdd(raw_posting_date, year, billing_month_num)
        is_valid_card = raw_card_last4.isdigit() and len(raw_card_last4) == 4
        card_last4 = raw_card_last4 if is_valid_card else None

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant_name,
            amount=amount,
            posting_date=posting_date,
            card_last4=card_last4,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的交易行: %s", row)
        return None


def _parse_mmdd(raw: str, year: int, billing_month_num: int = 0) -> date | None:
    """Parse an 'MM/DD' string into a Python date using the given year.

    When ``billing_month_num`` (1-12) is provided and the parsed month
    exceeds it, the transaction belongs to the prior calendar year (a
    January bill listing December purchases), so the year is rolled back by
    one — matching the fubon/ubot cross-year convention. ``0`` (default)
    keeps the supplied ``year`` unchanged for backward compatibility.

    Args:
        raw: Date string in 'MM/DD' format.
        year: Calendar year to use for the resulting date.
        billing_month_num: Billing month (1-12) for cross-year correction.

    Returns:
        Parsed date, or None if the string does not match 'MM/DD'.
    """
    match = _RE_DATE_MMDD.match(raw)
    if not match:
        return None
    mm = int(match.group(1))
    cross_year = billing_month_num > 0 and mm > billing_month_num
    resolved_year = year - 1 if cross_year else year
    return date(resolved_year, mm, int(match.group(2)))


# -- ROC format helpers (real CTBC PDFs) --


def _extract_billing_month_roc(first_page_text: str) -> str | None:
    """Extract billing month from first-line ROC format: '115 03 1 / 3'."""
    match = _RE_BILLING_LINE_ROC.search(first_page_text)
    if not match:
        return None
    roc_year = int(match.group(1))
    month = int(match.group(2))
    ad_year = roc_year + _ROC_OFFSET
    return f"{ad_year}-{month:02d}"


def _extract_due_date_roc(text: str, billing_month: str) -> date | None:
    """Extract the due date from ROC date format on the payment-slip page.

    The slip can carry stray ROC dates (e.g. a posting/print date) besides the
    cutoff, so blindly taking the last match is fragile. Candidates are filtered
    to the plausible due-date window — within the billing month through ~mid of
    the following month (CTBC's nominal cutoff is day 28 of the billing month) —
    and the last in-window match is returned. Returns None when no candidate
    fits, so the caller falls back to the page-1 day-28 estimate.
    """
    matches = _RE_ROC_DATE.findall(text)
    if not matches:
        return None
    try:
        billing_year, billing_month_num = (int(p) for p in billing_month.split("-"))
        window_start = date(billing_year, billing_month_num, 1)
    except (ValueError, IndexError):
        # Malformed billing_month — preserve the legacy last-match behaviour.
        roc_year, month, day = matches[-1]
        return _roc_to_date(int(roc_year), int(month), int(day))
    window_end = window_start + timedelta(days=45)
    candidate: date | None = None
    for roc_year, month, day in matches:
        try:
            parsed = _roc_to_date(int(roc_year), int(month), int(day))
        except ValueError:
            continue
        if window_start <= parsed <= window_end:
            candidate = parsed  # keep the last in-window match
    return candidate


def _extract_total_amount_dollar(text: str) -> int | None:
    """Extract total amount from dollar-prefixed format on payment slip page.

    Expects text from the last page where '$AMOUNT' is the total payable.
    """
    match = _RE_DOLLAR_AMOUNT.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


_RE_PAGE1_AMOUNT_GENERIC = re.compile(r"^(\d[\d,]*)\s+[\d.]+%$", re.MULTILINE)


def _extract_total_amount_page1(first_page_text: str) -> int | None:
    """Extract total_amount from page 1 for zero-balance 2-page bills.

    First tries to find the interest rate on the rate line (e.g. '113/01 7.58')
    and match 'AMOUNT RATE%' specifically.  Falls back to a generic
    'AMOUNT RATE%' line pattern when no rate line exists (newer format).
    Returns 0 for zero-balance months; None if the pattern cannot be found.
    """
    rate_match = _RE_PAGE1_RATE_LINE.search(first_page_text)
    if rate_match:
        rate_str = rate_match.group(1)
        amount_re = re.compile(rf"(\d[\d,]*)\s+{re.escape(rate_str)}%")
        matches = amount_re.findall(first_page_text)
        if matches:
            return int(matches[-1].replace(",", ""))
    # Fallback: match any "NUMBER RATE%" line on page 1 (e.g. "0 15%")
    matches = _RE_PAGE1_AMOUNT_GENERIC.findall(first_page_text)
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def _extract_due_date_page1(first_page_text: str) -> tuple[date, bool] | None:
    """Extract due date from page 1 when no payment slip page exists.

    Returns a ``(due_date, estimated)`` pair, or ``None`` if no ROC
    year/month token is present at all.

    Resolution order:
    1. Prefer a complete ROC date (``NNN/MM/DD``) on page 1 — this is the
       statement's exact cutoff and is **not** estimated (``estimated=False``).
    2. Otherwise fall back to year+month only (e.g. '113/01') and estimate the
       cutoff as day 28 per CTBC's nominal due day (``estimated=True``). The
       real cutoff varies by month-end / holiday順延, so an over-estimate can
       push a reminder too late — callers should widen reminder windows when
       this flag is set.
    """
    full_match = _RE_ROC_DATE.search(first_page_text)
    if full_match is not None:
        roc_year, month, day = full_match.groups()
        return _roc_to_date(int(roc_year), int(month), int(day)), False

    matches = _RE_ROC_YEAR_MONTH.findall(first_page_text)
    if not matches:
        return None
    roc_year_str, month_str = matches[-1]
    roc_year = int(roc_year_str)
    month = int(month_str)
    logger.warning(
        "CTBC 無法取得精確繳費截止日，估算為 %d/%02d/28 (ROC)", roc_year, month
    )
    return _roc_to_date(roc_year, month, 28), True


# -- OCR legacy format helpers (old CTBC PDFs with garbled font encoding) --


def _extract_billing_month_ocr_legacy(text: str) -> str | None:
    """Extract billing month from old CTBC OCR text: '103年 09月'."""
    match = _RE_BILLING_MONTH_OCR_LEGACY.search(text)
    if not match:
        return None
    roc_year = int(match.group(1))
    month = int(match.group(2))
    ad_year = roc_year + _ROC_OFFSET
    return f"{ad_year}-{month:02d}"


def _extract_due_date_ocr_legacy(text: str) -> date | None:
    """Extract due date from old CTBC OCR text: '繳款截止日 103/09/28'."""
    match = _RE_DUE_DATE_OCR_LEGACY.search(text)
    if not match:
        return None
    return _roc_to_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _extract_total_amount_ocr_legacy(text: str) -> int | None:
    """Extract total amount from old CTBC OCR text: '本期應繳總金額 133'."""
    match = _RE_TOTAL_AMOUNT_OCR_LEGACY.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


# Merchant image detection thresholds (CTBC PDF layout-specific).
# Merchant name images start at x ~ 125, distinguishable from icons/logos
# by their minimum width.
_MERCHANT_IMG_X0_MIN = 120.0
_MERCHANT_IMG_X0_MAX = 135.0
_MERCHANT_IMG_MIN_WIDTH = 30.0


def _find_merchant_images(
    page: pdfplumber.page.Page,
) -> list[dict[str, float]]:
    """Find merchant name images in the transaction area.

    CTBC PDFs render merchant names as images at x ~ 125.
    Returns a list of image bounding boxes sorted by y position.
    """
    return sorted(
        [
            img
            for img in page.images
            if _MERCHANT_IMG_X0_MIN < float(img["x0"]) < _MERCHANT_IMG_X0_MAX
            and float(img["width"]) > _MERCHANT_IMG_MIN_WIDTH
        ],
        key=lambda img: float(img["top"]),
    )


def _ocr_merchant_image(
    page: pdfplumber.page.Page,
    img_bbox: dict[str, float],
) -> str:
    """Crop a merchant image region and OCR it.

    Returns the raw recognized text, or empty string on failure. Merchant-name
    normalization is applied once downstream in ``_parse_roc_transaction`` via
    the unified ``normalize_ocr_merchant`` (single SSOT in ``ocr_postprocess``).
    """
    if not is_ocr_available():
        return ""

    try:
        x0 = float(img_bbox["x0"])
        top = float(img_bbox["top"])
        x1 = float(img_bbox["x1"])
        bottom = float(img_bbox["bottom"])
        cropped = page.crop((x0, top, x1, bottom))
        pil_image = cropped.to_image(resolution=300).original
        return extract_text_from_image(pil_image)
    except (ValueError, AttributeError, OSError):
        logger.warning(
            "商戶圖片 OCR 失敗: x=%.0f y=%.0f",
            img_bbox["x0"],
            img_bbox["top"],
            exc_info=True,
        )
        return ""


def _match_merchant_to_transaction(
    merchant_images: list[dict[str, float]],
    page: pdfplumber.page.Page,
    used_indices: set[int],
) -> str:
    """Assign the next unused merchant image to a transaction.

    Merchant images and transaction lines appear in the same top-to-bottom
    order, so we assign them sequentially by encounter order.
    """
    if not merchant_images:
        return ""

    for i, img in enumerate(merchant_images):
        if i not in used_indices:
            used_indices.add(i)
            return _ocr_merchant_image(page, img)

    return ""


def _extract_transactions_roc(
    pages: list[pdfplumber.page.Page],
) -> list[TransactionItem]:
    """Extract transactions from text lines in ROC date format.

    Pattern: 'YYY/MM/DD YYY/MM/DD AMOUNT CARD4 CURRENCY'
    Merchant names are extracted via OCR from embedded images when
    tesseract is available; otherwise falls back to empty string.
    """
    items: list[TransactionItem] = []
    for page in pages:
        text = page.extract_text() or ""
        merchant_images = _find_merchant_images(page)
        used_indices: set[int] = set()

        for match in _RE_TRANSACTION_LINE_ROC.finditer(text):
            merchant = _match_merchant_to_transaction(
                merchant_images, page, used_indices
            )
            if _is_non_transaction_merchant(merchant):
                logger.debug(
                    "跳過非交易行（已知標題）：merchant=%s, line=%s",
                    merchant,
                    match.group(0),
                )
                continue
            item = _parse_roc_transaction(match, merchant=merchant)
            if item is not None:
                items.append(item)
    return items


def _parse_roc_transaction(
    match: re.Match[str],
    *,
    merchant: str = "",
) -> TransactionItem | None:
    """Parse a single ROC-format transaction line."""
    try:
        raw_trans = match.group(1)
        raw_posting = match.group(2)
        raw_amount = match.group(3)
        card_last4 = match.group(4)
        # group(5) is currency code (TW, US, etc.) -- not stored separately

        ty, tm, td = raw_trans.split("/")
        trans_date = _roc_to_date(int(ty), int(tm), int(td))

        py_, pm, pd = raw_posting.split("/")
        posting_date = _roc_to_date(int(py_), int(pm), int(pd))

        # 退款保留為負數明細（與 refund_policy 一致）。ROC 行 regex 的金額僅含
        # 數字，故負數化完全依 OCR 商戶名是否為退款措辭判定（-abs 防重複負數化）。
        merchant_name = normalize_ocr_merchant(merchant)
        amount = parse_amount_cell(raw_amount)
        if is_refund_merchant(merchant_name):
            amount = -abs(amount)

        return TransactionItem(
            trans_date=trans_date,
            merchant=merchant_name,
            amount=amount,
            posting_date=posting_date,
            card_last4=card_last4,
        )
    except (ValueError, IndexError):
        logger.warning("跳過無法解析的 ROC 交易行: %s", match.group(0))
        return None


# Module-level registration
registry.register(CtbcV1Parser())
