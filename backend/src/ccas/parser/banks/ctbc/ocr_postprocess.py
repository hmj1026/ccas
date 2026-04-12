"""Post-processing for CTBC OCR/PDF text extraction corruption.

Only deterministic corrections are applied: corruption patterns that are
stable and whose correct form is unambiguous. Ambiguous or one-off cases
are left raw so downstream review can catch them.
"""

from __future__ import annotations

import re

_BRAND_CORRECTIONS: dict[str, str] = {
    "百鋼": "百貨",
    "斷體": "超商",
    "全中": "全聯",
    "拍孚": "拍賣",
    "拍賈": "拍賣",
    "統一時代百鋼": "統一時代百貨",
    "統一超商斷體": "統一超商",
    "全家斷體": "全家便利商店",
}

# `一` is only a corrupted dash when wedged between ASCII characters. Inside
# Chinese phrases (`統一`, `一卡通`) it is a regular character and must be kept.
_HYPHEN_PATTERN = re.compile(r"(?<=[A-Za-z0-9])一(?=[A-Za-z0-9])")


def normalize_ocr_merchant(raw: str) -> str:
    """Return ``raw`` with known OCR corruption patterns corrected.

    The brand whitelist runs before the hyphen pass so multi-character
    corrections match the raw form before ASCII-adjacent characters are
    rewritten.
    """
    if not raw:
        return raw

    cleaned = raw
    for wrong, right in _BRAND_CORRECTIONS.items():
        if wrong in cleaned:
            cleaned = cleaned.replace(wrong, right)

    cleaned = _HYPHEN_PATTERN.sub("-", cleaned)
    return cleaned
