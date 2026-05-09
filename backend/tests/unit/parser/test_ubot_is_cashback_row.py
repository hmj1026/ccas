"""Tests for UBOT cashback/refund row filter."""

from __future__ import annotations

from ccas.parser.banks.ubot_v1 import _is_cashback_row


def test_cashback_prefix_is_filtered() -> None:
    assert _is_cashback_row(
        "03/05 03/05 現金回饋－吉鶴卡日幣回饋 3",
        "現金回饋－吉鶴卡日幣回饋",
        3,
    )
    assert _is_cashback_row("03/05 03/05 回饋入帳 150", "回饋入帳", 150)
    assert _is_cashback_row("03/05 03/05 紅利折抵 500", "紅利折抵", 500)
    assert _is_cashback_row("03/05 03/05 沖銷利息 100", "沖銷利息", 100)


def test_negative_amount_is_cashback() -> None:
    assert _is_cashback_row(
        "03/05 03/05 專案：想分調整全球人壽 -12152",
        "專案：想分調整全球人壽",
        -12152,
    )


def test_line_prefix_dash_is_cashback() -> None:
    assert _is_cashback_row("(-) 03/05 某交易 500", "某交易", 500)
    assert _is_cashback_row("－03/05 某交易 500", "某交易", 500)


def test_normal_consumption_not_flagged() -> None:
    assert not _is_cashback_row("03/05 03/05 全聯福利中心 800", "全聯福利中心", 800)
    assert not _is_cashback_row("03/05 03/05 星巴克 120", "星巴克", 120)


def test_merchant_mid_word_cashback_not_flagged() -> None:
    assert not _is_cashback_row(
        "03/05 03/05 好運回饋商行 2000",
        "好運回饋商行",
        2000,
    )
