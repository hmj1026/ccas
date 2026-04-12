"""Tests for CTBC OCR post-processing."""

from __future__ import annotations

from ccas.parser.banks.ctbc.ocr_postprocess import normalize_ocr_merchant


def test_hyphen_between_ascii_becomes_dash() -> None:
    assert normalize_ocr_merchant("ICP一CS") == "ICP-CS"
    assert normalize_ocr_merchant("P一C") == "P-C"
    assert normalize_ocr_merchant("01一06") == "01-06"


def test_preserves_yi_inside_chinese_phrases() -> None:
    assert normalize_ocr_merchant("統一超商") == "統一超商"
    assert normalize_ocr_merchant("統一時代") == "統一時代"
    assert normalize_ocr_merchant("本行扣繳") == "本行扣繳"


def test_brand_whitelist_fixes_known_corruption() -> None:
    assert "百鋼" not in normalize_ocr_merchant("統一時代百鋼")
    assert "百貨" in normalize_ocr_merchant("統一時代百鋼")
    assert "百貨" in normalize_ocr_merchant("新光三越百鋼")


def test_empty_string_returns_empty() -> None:
    assert normalize_ocr_merchant("") == ""


def test_whitelist_runs_before_hyphen_normalization() -> None:
    # 拍孚 is a whitelist entry → 拍賣. 一 here is between ASCII `i` and CJK
    # `拍`, so the hyphen rule does NOT apply (one side non-ASCII). Result
    # keeps `一` and fixes the brand token.
    assert normalize_ocr_merchant("Pi一拍孚") == "Pi一拍賣"


def test_mixed_case_ascii_dash_and_brand_fix() -> None:
    # Input simulates `ICP-CS 統一時代百鋼` rendered with both corruption types.
    assert (
        normalize_ocr_merchant("ICP一CS 統一時代百鋼")
        == "ICP-CS 統一時代百貨"
    )
