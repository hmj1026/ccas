"""Post-processing for CTBC OCR/PDF text extraction corruption.

Only deterministic corrections are applied: corruption patterns that are
stable and whose correct form is unambiguous. Ambiguous or one-off cases
are left raw so downstream review can catch them.
"""

from __future__ import annotations

import re

# Regex-based corrections for merchant-name image OCR. Migrated verbatim (SSOT
# unification) from ``ctbc_v1._OCR_MERCHANT_NORMALIZATION_RULES``; these target
# multi-glyph corruptions in the merchant-image OCR path (e.g. mangled
# ``7-ELEVEN`` / ``全家便利商店`` runs). Applied **before** the brand-string
# corrections below to reproduce the original combined order: the merchant-image
# path previously ran the regex rules first (in ``_ocr_merchant_image``) and the
# brand/hyphen pass second (in ``_parse_roc_transaction``).
_OCR_REGEX_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("Pi一金家便利商店", "全家便利商店"),
    ("Pi一全家便利商店", "全家便利商店"),
    (r"Pi一了Y[一了]+ELEVEN", "7-ELEVEN"),
    (r"PIiI一了Y一ELEVEN", "7-ELEVEN"),
    ("連加未麥芝勞", "麥當勞"),
    ("台灣麥當馮", "麥當勞"),
    ("無印恨品", "無印良品"),
)

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

    Single SSOT for CTBC merchant-name OCR cleanup. Passes run in a fixed
    order, matching the original combined merchant-image path byte-for-byte:

    1. ``_OCR_REGEX_CORRECTIONS`` — regex rewrites of multi-glyph corruptions.
    2. ``_BRAND_CORRECTIONS`` — string brand-token whitelist; runs before the
       hyphen pass so multi-character corrections match the raw form first.
    3. ``_HYPHEN_PATTERN`` — ASCII-adjacent ``一`` → ``-``.
    """
    if not raw:
        return raw

    cleaned = raw
    for pattern, replacement in _OCR_REGEX_CORRECTIONS:
        cleaned = re.sub(pattern, replacement, cleaned)

    for wrong, right in _BRAND_CORRECTIONS.items():
        if wrong in cleaned:
            cleaned = cleaned.replace(wrong, right)

    cleaned = _HYPHEN_PATTERN.sub("-", cleaned)
    return cleaned
