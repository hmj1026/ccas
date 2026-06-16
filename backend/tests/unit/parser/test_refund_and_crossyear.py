"""Cross-bank tests for the Stage-1 parser-correctness fixes.

Covers:
- Cathay total amount prefers 本期應繳總額 over 本期最低應繳金額
- Cathay / Fubon cross-year MM/DD (a January bill listing December transactions)
- Refund-merchant rows kept as negative across Cathay / Fubon / Taishin
- Parenthesised table-cell amounts parsed as credits
- Fubon's deliberate payment-line skip stays intact
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pdfplumber.page

from ccas.parser.banks.cathay_v1 import CathayV1Parser
from ccas.parser.banks.fubon_v1 import FubonV1Parser
from ccas.parser.banks.taishin_v1 import TaishinV1Parser

from .conftest import (
    CATHAY_TABLE_HEADER_ROW,
    FUBON_TABLE_HEADER_ROW,
    TAISHIN_TABLE_HEADER_ROW,
    make_mock_page,
)


def _pages_with_table(
    header: list[str], rows: list[list[str]]
) -> list[pdfplumber.page.Page]:
    table = [header, *rows]
    return cast(list[pdfplumber.page.Page], [make_mock_page("", tables=[table])])


def _pages_with_text(text: str) -> list[pdfplumber.page.Page]:
    return cast(list[pdfplumber.page.Page], [make_mock_page(text)])


# -- Cathay total amount precision --


class TestCathayTotalAmountPrecision:
    def test_prefers_total_over_minimum_even_when_minimum_first(self) -> None:
        parser = CathayV1Parser()
        text = (
            "國泰世華銀行 信用卡\n"
            "本期最低應繳金額：NT$ 1,000\n"
            "本期應繳總額：NT$ 12,345\n"
        )
        assert parser._extract_total_amount(text) == 12345

    def test_minimum_only_does_not_match(self) -> None:
        parser = CathayV1Parser()
        text = "國泰世華銀行 信用卡\n本期最低應繳金額：NT$ 1,000\n"
        assert parser._extract_total_amount(text) is None


# -- Cross-year MM/DD --


class TestCrossYearMmdd:
    def test_cathay_january_bill_dec_transaction_is_prior_year(self) -> None:
        parser = CathayV1Parser()
        rows = [["12/15", "12/17", "2345", "誠品書店", "980"]]
        txns = parser._extract_transactions(
            _pages_with_table(CATHAY_TABLE_HEADER_ROW, rows), 2026, 1
        )
        assert len(txns) == 1
        assert txns[0].trans_date == date(2025, 12, 15)

    def test_cathay_same_month_not_shifted(self) -> None:
        parser = CathayV1Parser()
        rows = [["01/15", "01/17", "2345", "誠品書店", "980"]]
        txns = parser._extract_transactions(
            _pages_with_table(CATHAY_TABLE_HEADER_ROW, rows), 2026, 1
        )
        assert txns[0].trans_date == date(2026, 1, 15)

    def test_fubon_january_bill_dec_transaction_is_prior_year(self) -> None:
        parser = FubonV1Parser()
        rows = [["12/20", "12/22", "8899", "全聯福利中心", "680"]]
        txns = parser._extract_transactions(
            _pages_with_table(FUBON_TABLE_HEADER_ROW, rows), 2026, 1
        )
        assert txns[0].trans_date == date(2025, 12, 20)


# -- Refund negation --


class TestRefundNegation:
    def test_cathay_table_refund_merchant_is_negative(self) -> None:
        parser = CathayV1Parser()
        rows = [["03/05", "03/07", "2345", "退款－誠品書店", "980"]]
        txns = parser._extract_transactions(
            _pages_with_table(CATHAY_TABLE_HEADER_ROW, rows), 2026
        )
        assert txns[0].amount == -980

    def test_cathay_parenthesised_amount_is_negative(self) -> None:
        parser = CathayV1Parser()
        rows = [["03/05", "03/07", "2345", "誠品書店", "(980)"]]
        txns = parser._extract_transactions(
            _pages_with_table(CATHAY_TABLE_HEADER_ROW, rows), 2026
        )
        assert txns[0].amount == -980

    def test_cathay_text_refund_merchant_is_negative(self) -> None:
        parser = CathayV1Parser()
        txns = parser._extract_transactions(
            _pages_with_text("2026/03/05 退款處理 980\n"), 2026
        )
        assert txns[0].amount == -980

    def test_cathay_lookalike_merchant_stays_positive(self) -> None:
        # 「退休俱樂部」mid-word 「退」 must not be treated as a refund.
        parser = CathayV1Parser()
        rows = [["03/05", "03/07", "2345", "退休俱樂部", "980"]]
        txns = parser._extract_transactions(
            _pages_with_table(CATHAY_TABLE_HEADER_ROW, rows), 2026
        )
        assert txns[0].amount == 980

    def test_fubon_table_refund_merchant_is_negative(self) -> None:
        parser = FubonV1Parser()
        rows = [["03/05", "03/07", "8899", "退費－某商家", "680"]]
        txns = parser._extract_transactions(
            _pages_with_table(FUBON_TABLE_HEADER_ROW, rows), 2026
        )
        assert txns[0].amount == -680

    def test_fubon_payment_line_still_skipped(self) -> None:
        # Deliberate behaviour preserved: free-text negative payment lines drop.
        parser = FubonV1Parser()
        txns = parser._extract_transactions(
            _pages_with_text("115/03/25 自動扣繳 115/03/26 -3,793\n"), 2026
        )
        assert len(txns) == 0

    def test_taishin_table_refund_merchant_is_negative(self) -> None:
        parser = TaishinV1Parser()
        rows = [["03/03", "03/05", "6789", "退款－某商家", "520"]]
        txns = parser._extract_transactions(
            _pages_with_table(TAISHIN_TABLE_HEADER_ROW, rows), 2026
        )
        assert txns[0].amount == -520

    def test_taishin_real_positive_refund_is_negative(self) -> None:
        parser = TaishinV1Parser()
        txns = parser._extract_transactions(
            _pages_with_text("109/01/05 109/01/06 退款處理 500\n"), 2026
        )
        assert len(txns) == 1
        assert txns[0].amount == -500

    def test_taishin_real_payment_already_negative_preserved(self) -> None:
        parser = TaishinV1Parser()
        txns = parser._extract_transactions(
            _pages_with_text("108/12/27 108/12/27 您的付款已收到，謝謝您！ -18,901\n"),
            2026,
        )
        assert len(txns) == 1
        assert txns[0].amount == -18901
