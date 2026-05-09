"""CAPTCHA 圖片 OCR 辨識。

使用 pytesseract 進行 CAPTCHA 圖片的文字辨識。
"""

from __future__ import annotations

import logging

from ccas.ingestor.fetcher.base import FetchError

logger = logging.getLogger(__name__)


def solve_captcha(image_bytes: bytes) -> str:
    """使用 pytesseract OCR 辨識 CAPTCHA 圖片。

    Args:
        image_bytes: CAPTCHA 圖片的原始位元組。

    Returns:
        辨識出的文字（英數字）；辨識失敗時回傳空字串。

    Raises:
        FetchError: tesseract 依賴未安裝或不可用。
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise FetchError("CAPTCHA", f"tesseract 依賴未安裝: {exc}") from exc

    try:
        import io

        image = Image.open(io.BytesIO(image_bytes))
        config = (
            "--psm 7 -c tessedit_char_whitelist="
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        )
        result = pytesseract.image_to_string(image, config=config).strip()
        logger.debug("CAPTCHA OCR 結果: %s", result)
        return result
    except pytesseract.TesseractNotFoundError as exc:
        raise FetchError("CAPTCHA", f"tesseract 執行檔不可用: {exc}") from exc
    except Exception:
        logger.warning("CAPTCHA OCR 辨識失敗", exc_info=True)
        return ""
