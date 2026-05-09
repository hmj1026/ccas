"""FUBON captcha OCR with confidence + length gating.

Primary recognition path: ``ddddocr`` — a captcha-specialized ONNX CNN. The
``DdddOcr`` instance is lazily initialized once per process (model bundle
~54 MB ships inside the wheel, no remote download required). Results must pass
a conservative gate before being returned:

    1. text is exactly 4 characters
    2. text is all digits 0-9
    3. aggregate confidence >= 0.80

Samples that fail the gate (or trigger an inference error) return ``None``,
signalling the caller to refetch the captcha and retry. This trades recall for
precision (no false positives) and relies on retry to reach the target
success rate. Empirical baseline on the shipped fixture set is ~90%.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import Any

import ddddocr  # type: ignore[import-untyped]
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

_MIN_CONF: float = 0.80
_EXPECTED_LEN: int = 4
# Defense in depth: cap the bytes fed into opencv/onnxruntime decoders.
# Real FUBON captchas are well under 10 KB; 512 KB leaves generous headroom
# while bounding the parser surface if upstream ever returns a malformed blob.
_MAX_CAPTCHA_BYTES: int = 512 * 1024

_OCR: ddddocr.DdddOcr | None = None
_OCR_LOCK = threading.Lock()


@dataclass(frozen=True)
class CaptchaResult:
    text: str
    confidence: float


def _get_ocr() -> ddddocr.DdddOcr:
    global _OCR
    if _OCR is None:
        with _OCR_LOCK:
            if _OCR is None:
                _OCR = ddddocr.DdddOcr(show_ad=False, beta=False)
    return _OCR


def _preprocess(jpeg_bytes: bytes) -> bytes:
    """Enhance captcha image for better OCR accuracy.

    Pipeline: grayscale → contrast boost → Otsu-style binarization → median denoise.
    Returns processed JPEG bytes; falls back to original on any error.
    """
    try:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.0)
        thresh = _otsu_threshold(img)
        lut = [255 if i > thresh else 0 for i in range(256)]
        img = img.point(lut, mode="1")
        img = img.convert("L").filter(ImageFilter.MedianFilter(size=3))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        logger.debug("captcha_preprocess_fallback", exc_info=True)
        return jpeg_bytes


def _otsu_threshold(img: Image.Image) -> int:
    """Compute Otsu's optimal binarization threshold for a grayscale image."""
    histogram = img.histogram()
    total = sum(histogram)
    sum_all = sum(i * h for i, h in enumerate(histogram))
    sum_bg = 0.0
    weight_bg = 0
    best_thresh = 0
    best_variance = 0.0
    for t in range(256):
        weight_bg += histogram[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * histogram[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > best_variance:
            best_variance = variance
            best_thresh = t
    return best_thresh


def solve(jpeg_bytes: bytes) -> CaptchaResult | None:
    """Run OCR on a FUBON captcha JPEG and apply the conf+length+digit gate.

    Returns:
        ``CaptchaResult`` when the gate accepts; ``None`` when the result
        should be rejected and the caller should refetch + retry.
    """
    if len(jpeg_bytes) > _MAX_CAPTCHA_BYTES:
        logger.warning("fubon_captcha_oversized", extra={"size": len(jpeg_bytes)})
        return None
    processed = _preprocess(jpeg_bytes)
    try:
        result: Any = _get_ocr().classification(processed, probability=True)
    except Exception:  # noqa: BLE001 -- ddddocr raises broad types on bad input
        logger.warning("fubon_captcha_ocr_error", exc_info=True)
        return None

    if not isinstance(result, dict):
        return None

    raw_text = result.get("text")
    raw_conf = result.get("confidence")
    if raw_text is None or raw_conf is None:
        return None

    text = str(raw_text)
    try:
        confidence = float(raw_conf)
    except (TypeError, ValueError):
        return None

    if len(text) != _EXPECTED_LEN:
        return None
    if not text.isdigit():
        return None
    if confidence < _MIN_CONF:
        return None
    return CaptchaResult(text=text, confidence=confidence)
