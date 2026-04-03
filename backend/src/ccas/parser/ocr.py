"""OCR support for PDF parser.

Provides optional tesseract OCR integration with graceful fallback
when tesseract is not installed.
"""

from __future__ import annotations

import functools
import logging
import shutil

from PIL import Image

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
) -> str:
    """Extract text from a PIL Image using tesseract OCR.

    Args:
        image: PIL Image to process.
        lang: Tesseract language code (default: Traditional Chinese).

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
            config="--psm 7",  # single line mode
        )
        return text.strip()
    except (RuntimeError, OSError):
        logger.warning("OCR 辨識失敗", exc_info=True)
        return ""
