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

import logging
import threading
from dataclasses import dataclass
from typing import Any

import ddddocr  # type: ignore[import-untyped]

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


def solve(jpeg_bytes: bytes) -> CaptchaResult | None:
    """Run OCR on a FUBON captcha JPEG and apply the conf+length+digit gate.

    Returns:
        ``CaptchaResult`` when the gate accepts; ``None`` when the result
        should be rejected and the caller should refetch + retry.
    """
    if len(jpeg_bytes) > _MAX_CAPTCHA_BYTES:
        logger.warning(
            "fubon_captcha_oversized", extra={"size": len(jpeg_bytes)}
        )
        return None
    try:
        result: Any = _get_ocr().classification(jpeg_bytes, probability=True)
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
