"""Tests for the shared refund / credit detection helpers."""

from __future__ import annotations

import pytest

from ccas.parser.refund_utils import is_refund_merchant, parse_amount_cell


class TestIsRefundMerchant:
    def test_prefix_keyword_is_refund(self) -> None:
        assert is_refund_merchant("退款－某商家")
        assert is_refund_merchant("退費")
        assert is_refund_merchant("沖銷利息")
        assert is_refund_merchant("取消授權 某筆")

    def test_leading_whitespace_tolerated(self) -> None:
        assert is_refund_merchant("  退款 某商家")

    def test_mid_word_keyword_is_not_refund(self) -> None:
        # 「退」在商家中段不算（避免誤殺「退休俱樂部」等合法商家）。
        assert not is_refund_merchant("退休俱樂部")
        assert not is_refund_merchant("星巴克")

    def test_empty_is_not_refund(self) -> None:
        assert not is_refund_merchant("")
        assert not is_refund_merchant("   ")

    def test_extra_keywords_extend_match(self) -> None:
        assert not is_refund_merchant("永豐自扣已入帳")
        assert is_refund_merchant("永豐自扣已入帳", extra_keywords=("永豐自扣",))


class TestParseAmountCell:
    def test_plain_positive(self) -> None:
        assert parse_amount_cell("500") == 500
        assert parse_amount_cell("1,450") == 1450

    def test_leading_minus_is_negative(self) -> None:
        assert parse_amount_cell("-500") == -500
        assert parse_amount_cell("－7,147") == -7147

    def test_parentheses_are_negative(self) -> None:
        assert parse_amount_cell("(500)") == -500
        assert parse_amount_cell("（1,200）") == -1200

    def test_whitespace_stripped(self) -> None:
        assert parse_amount_cell("  500  ") == 500

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_amount_cell("not-a-number")
        with pytest.raises(ValueError):
            parse_amount_cell("")
