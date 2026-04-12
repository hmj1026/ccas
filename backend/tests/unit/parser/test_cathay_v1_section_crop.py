"""Tests for Cathay v1 parser cropping / header heuristics."""

from __future__ import annotations

from ccas.parser.banks.cathay_v1 import (
    _NON_TRANSACTION_SECTION_ANCHORS,
    _crop_transaction_section,
    _is_transaction_table,
)


def test_crop_removes_installment_section() -> None:
    text = (
        "消費明細\n"
        "01/15 星巴克 120\n"
        "01/20 全聯 500\n"
        "帳單分期資訊\n"
        "帳單分期 12-12 33,293 2,774\n"
    )
    cropped = _crop_transaction_section(text)
    assert "星巴克" in cropped
    assert "全聯" in cropped
    assert "帳單分期" not in cropped


def test_crop_removes_reward_sections() -> None:
    for anchor in ("紅利點數", "優惠回饋", "本期回饋", "累積紅利", "循環信用"):
        text = f"消費明細\n01/15 星巴克 120\n{anchor}\n抽獎活動 100\n"
        cropped = _crop_transaction_section(text)
        assert "星巴克" in cropped
        assert anchor not in cropped


def test_crop_is_noop_when_no_anchor() -> None:
    text = "消費明細\n01/15 星巴克 120\n01/20 全聯 500\n"
    assert _crop_transaction_section(text) == text


def test_non_transaction_anchors_contains_expected_set() -> None:
    assert "帳單分期" in _NON_TRANSACTION_SECTION_ANCHORS
    assert "紅利點數" in _NON_TRANSACTION_SECTION_ANCHORS
    assert "優惠回饋" in _NON_TRANSACTION_SECTION_ANCHORS


def test_is_transaction_table_requires_date_and_amount_headers() -> None:
    assert _is_transaction_table([["交易日", "商店名稱", "金額"]])
    assert _is_transaction_table([["消費日", "商店", "新臺幣金額"]])


def test_is_transaction_table_rejects_amount_only_header() -> None:
    assert not _is_transaction_table([["項目", "金額"]])
    assert not _is_transaction_table([["分期期數", "本期應付金額", "剩餘期數"]])


def test_is_transaction_table_rejects_date_only_header() -> None:
    assert not _is_transaction_table([["交易日", "商店"]])
