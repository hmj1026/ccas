"""Tests for SINOPAC refund row filter."""

from __future__ import annotations

from ccas.parser.banks.sinopac_v1 import _is_refund_row


def test_merchant_prefix_match_is_refund() -> None:
    assert _is_refund_row("01/15 退款－某商家 1000", "退款－某商家", 1000)
    assert _is_refund_row("01/15 退費  500", "退費", 500)
    assert _is_refund_row("01/15 沖銷利息 100", "沖銷利息", 100)
    assert _is_refund_row("01/15 永豐自扣已入帳 16652", "永豐自扣已入帳，謝謝！", 16652)


def test_negative_amount_is_refund() -> None:
    assert _is_refund_row("01/15 某消費 -1500", "某消費", -1500)


def test_line_starting_with_minus_prefix_is_refund() -> None:
    assert _is_refund_row("(-) 01/15 某交易 500", "某交易", 500)
    assert _is_refund_row("－01/15 某交易 500", "某交易", 500)


def test_normal_consumption_is_not_refund() -> None:
    assert not _is_refund_row("01/15 星巴克 120", "星巴克", 120)
    assert not _is_refund_row("01/15 全聯 1560", "全聯福利中心", 1560)


def test_merchant_mid_word_keyword_is_not_refund() -> None:
    # 「退」在商家中段不算（避免誤殺「退休俱樂部」「退藏文物館」等合法商家）
    assert not _is_refund_row("01/15 退休俱樂部 2000", "退休俱樂部", 2000)


def test_large_amount_is_not_refund_when_positive() -> None:
    assert not _is_refund_row("01/15 大額消費 500000", "大額消費", 500000)
