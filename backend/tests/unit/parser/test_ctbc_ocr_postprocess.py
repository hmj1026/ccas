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
    assert normalize_ocr_merchant("ICP一CS 統一時代百鋼") == "ICP-CS 統一時代百貨"


# -- SSOT unification: former ctbc_v1 regex rules now live here too --


def test_applies_former_regex_corrections() -> None:
    # These came from ctbc_v1._OCR_MERCHANT_NORMALIZATION_RULES and must now be
    # applied by the unified normalize_ocr_merchant.
    assert normalize_ocr_merchant("Pi一金家便利商店") == "全家便利商店"
    assert normalize_ocr_merchant("Pi一全家便利商店") == "全家便利商店"
    assert normalize_ocr_merchant("Pi一了Y一ELEVEN") == "7-ELEVEN"
    assert normalize_ocr_merchant("Pi一了Y了一ELEVEN") == "7-ELEVEN"
    assert normalize_ocr_merchant("PIiI一了Y一ELEVEN") == "7-ELEVEN"
    assert normalize_ocr_merchant("連加未麥芝勞") == "麥當勞"
    assert normalize_ocr_merchant("台灣麥當馮") == "麥當勞"
    assert normalize_ocr_merchant("無印恨品") == "無印良品"


def test_regex_correction_runs_before_brand_and_hyphen() -> None:
    # `台灣麥當馮` (regex) fixed to `麥當勞`; the trailing `一489` keeps its `一`
    # because one side is CJK (廳), so the hyphen pass does not apply.
    assert normalize_ocr_merchant("台灣麥當馮餐廳一489") == "麥當勞餐廳一489"


def test_merged_function_applies_both_rule_sets_in_one_call() -> None:
    # Combined input exercises a regex correction (連加未麥芝勞→麥當勞), a brand
    # string correction (百鋼→百貨), and the ASCII-hyphen pass (A一B→A-B) in a
    # single pass, proving the two former rule sets are unified.
    assert (
        normalize_ocr_merchant("連加未麥芝勞 統一時代百鋼 ICP一CS")
        == "麥當勞 統一時代百貨 ICP-CS"
    )
