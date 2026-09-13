"""OCR support for PDF parser.

Provides optional tesseract OCR integration with graceful fallback
when tesseract is not installed.
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

from PIL import Image

from ccas.parser.result import ParseResult, finalize_parse_result

logger = logging.getLogger(__name__)


@functools.cache
def is_ocr_available() -> bool:
    """Check if tesseract OCR is installed and available.

    Result is cached for the process lifetime.
    Logs a WARNING once if tesseract is not found.
    """
    available = shutil.which("tesseract") is not None
    if not available:
        logger.warning(
            "tesseract 未安裝，商戶名稱 OCR 將略過。"
            "安裝方式：apt-get install tesseract-ocr tesseract-ocr-chi-tra"
        )
    return available


def extract_text_from_image(
    image: Image.Image,
    lang: str = "chi_tra",
    *,
    config: str = "--psm 7",
) -> str:
    """Extract text from a PIL Image using tesseract OCR.

    Args:
        image: PIL Image to process.
        lang: Tesseract language code (default: Traditional Chinese).
        config: Tesseract page segmentation configuration.

    Returns:
        Extracted text with whitespace stripped, or empty string on failure.
    """
    if not is_ocr_available():
        return ""

    try:
        import pytesseract

        text = pytesseract.image_to_string(
            image,
            lang=lang,
            config=config,
        )
        return text.strip()
    except Exception:  # noqa: BLE001 -- OCR backends raise varied exceptions
        logger.warning("OCR 辨識失敗", exc_info=True)
        return ""


def extract_text_from_pdf(
    pdf_path: Path,
    *,
    lang: str = "chi_tra",
    resolution: int = 300,
) -> str:
    """OCR every page of a scanned PDF and return text in page order.

    Rendering and OCR errors are isolated to the current page. An unavailable
    tesseract installation or a PDF that cannot be opened produces an empty
    result so orchestration can decide whether to try another route.
    """
    if not is_ocr_available():
        return ""

    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            page_texts: list[str] = []
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    image = page.to_image(resolution=resolution).original
                    text = extract_text_from_image(image, lang=lang, config="--psm 3")
                except Exception:  # noqa: BLE001 -- isolate one bad page
                    logger.warning(
                        "整頁 OCR 失敗: page=%d pdf=%s",
                        page_number,
                        pdf_path.name,
                        exc_info=True,
                    )
                    continue
                if text and text.strip():
                    page_texts.append(text.strip())
            return "\n".join(page_texts)
    except Exception:  # noqa: BLE001 -- malformed PDFs must reach orchestration
        logger.warning("整份 PDF OCR 失敗: pdf=%s", pdf_path.name, exc_info=True)
        return ""


def parse_ocr_text(text: str, bank_code: str) -> ParseResult | None:
    """Extract a conservative bill summary from OCR text.

    Bank-specific parsers remain the source of truth for detailed rows. This
    small adapter intentionally extracts only stable summary labels, allowing
    the ordered intake route to hand a scanned document to the next gate while
    leaving unsupported layouts for LLM or manual review.
    """
    month = _first_match(
        text,
        (
            re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),
            re.compile(r"(\d{4})\s*[-/]\s*(\d{1,2})"),
            re.compile(r"(\d{3})\s*/\s*(\d{1,2})"),
        ),
    )
    billing_month = ""
    if month is not None:
        year, month_number = (int(month[0]), int(month[1]))
        if year < 1911:
            year += 1911
        if 1 <= month_number <= 12:
            billing_month = f"{year:04d}-{month_number:02d}"

    due_date = _extract_ocr_date(
        text,
        r"(?:繳費|繳款|付款)截止日[^\d]*(\d{3,4})\s*[/年-]\s*(\d{1,2})\s*[/月-]\s*(\d{1,2})",
    )
    total_match = re.search(
        r"(?:本期應繳(?:總額|總金額|金額)|應繳總額)[^\d-]*([\d,]+)", text
    )
    total_amount = int(total_match.group(1).replace(",", "")) if total_match else -1

    if not billing_month and due_date is None and total_amount < 0:
        return None

    result = ParseResult(
        bank_code=bank_code if bank_code.strip() else "",
        billing_month=billing_month,
        total_amount=total_amount,
        due_date=due_date or date.min,
        transactions=(),
    )
    finalized = finalize_parse_result(result, method="ocr")
    if finalized.parse_confidence >= 1.0 and not finalized.needs_review:
        finalized = replace(finalized, parse_confidence=0.95)
    return finalized


def _first_match(
    text: str, patterns: tuple[re.Pattern[str], ...]
) -> tuple[str, str] | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1), match.group(2)
    return None


def _extract_ocr_date(text: str, pattern: str) -> date | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    year, month, day = (int(match.group(i)) for i in range(1, 4))
    if year < 1911:
        year += 1911
    try:
        return date(year, month, day)
    except ValueError:
        return None
