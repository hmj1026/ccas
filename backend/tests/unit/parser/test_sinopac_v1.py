"""SinopacV1Parser unit tests.

Tests internal methods (_identify, _extract_summary, _extract_transactions)
using text fixtures, not real PDFs.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock, patch

import pdfplumber.page
import pytest

from ccas.parser.base import ParseError

from .conftest import (
    EXPECTED_SINOPAC_BILLING_MONTH,
    EXPECTED_SINOPAC_DUE_DATE,
    EXPECTED_SINOPAC_REAL_BILLING_MONTH,
    EXPECTED_SINOPAC_REAL_DUE_DATE,
    EXPECTED_SINOPAC_REAL_TOTAL_AMOUNT,
    EXPECTED_SINOPAC_TOTAL_AMOUNT,
    SINOPAC_FIRST_PAGE_TEXT,
    SINOPAC_NON_SINOPAC_PAGE_TEXT,
    SINOPAC_REAL_FIRST_PAGE_TEXT,
    SINOPAC_REAL_TXN_PAGE_TEXT,
    SINOPAC_SUMMARY_MISSING_DUE_DATE_TEXT,
    SINOPAC_SUMMARY_MISSING_TOTAL_TEXT,
    SINOPAC_TABLE_HEADER_ROW,
    SINOPAC_TRANSACTION_ROWS,
    SINOPAC_ZERO_BALANCE_FIRST_PAGE_TEXT,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate SinopacV1Parser (deferred import)."""
    from ccas.parser.banks.sinopac_v1 import SinopacV1Parser

    return SinopacV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_sinopac_statement(self):
        parser = _make_parser()
        assert parser._identify(SINOPAC_FIRST_PAGE_TEXT) is True

    def test_rejects_non_sinopac_statement(self):
        parser = _make_parser()
        assert parser._identify(SINOPAC_NON_SINOPAC_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("永豐銀行 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(SINOPAC_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_SINOPAC_BILLING_MONTH
        assert total_amount == EXPECTED_SINOPAC_TOTAL_AMOUNT
        assert due_date == EXPECTED_SINOPAC_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(SINOPAC_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(SINOPAC_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = "永豐銀行 信用卡帳單\n繳費截止日：2026/04/20\n本期應繳總額：NT$ 100\n"
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [SINOPAC_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(SINOPAC_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 420
        assert txns[0].trans_date == date(2026, 3, 1)
        assert txns[0].posting_date == date(2026, 3, 3)
        assert txns[0].card_last4 == "5678"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([SINOPAC_TRANSACTION_ROWS[1]])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 1280

    def test_returns_empty_tuple_for_no_tables(self):
        parser = _make_parser()
        page = make_mock_page("no table content")

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert txns == ()

    def test_skips_malformed_row_with_warning(self, caplog):
        parser = _make_parser()
        bad_row = ["03/01", "", "", "", "not-a-number"]
        pages = self._make_pages_with_table([bad_row])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 0
        assert "跳過" in caplog.text or "warning" in caplog.text.lower()

    def test_multi_page_transactions(self):
        parser = _make_parser()
        table1 = [SINOPAC_TABLE_HEADER_ROW, SINOPAC_TRANSACTION_ROWS[0]]
        table2 = [SINOPAC_TABLE_HEADER_ROW, SINOPAC_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_sinopac(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(SINOPAC_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_sinopac(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(SINOPAC_NON_SINOPAC_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is False

    def test_can_parse_returns_false_on_error(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "corrupt.pdf"

        with patch("pdfplumber.open", side_effect=Exception("corrupt")):
            assert parser.can_parse(pdf_path) is False


# -- parse full flow test --


class TestParse:
    def test_parse_returns_complete_result(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        table = [SINOPAC_TABLE_HEADER_ROW, *SINOPAC_TRANSACTION_ROWS]
        mock_page = make_mock_page(SINOPAC_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "SINOPAC"
        assert result.billing_month == EXPECTED_SINOPAC_BILLING_MONTH
        assert result.total_amount == EXPECTED_SINOPAC_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_SINOPAC_DUE_DATE
        assert len(result.transactions) == 3


# -- Real-PDF format tests (no-colon due date, row-based total, MM/DD txns) --


class TestRealPdfFormat:
    """Tests exercising the actual SINOPAC PDF layout sampled from production."""

    def test_extracts_summary_without_colon(self):
        parser = _make_parser()
        page = make_mock_page(SINOPAC_REAL_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_SINOPAC_REAL_BILLING_MONTH
        assert total_amount == EXPECTED_SINOPAC_REAL_TOTAL_AMOUNT
        assert due_date == EXPECTED_SINOPAC_REAL_DUE_DATE

    def test_zero_balance_bill_raises_identifiable_parse_error(self):
        parser = _make_parser()
        page = make_mock_page(SINOPAC_ZERO_BALANCE_FIRST_PAGE_TEXT)

        with pytest.raises(ParseError, match="zero-balance"):
            parser._extract_summary([page])

    def test_extracts_transactions_from_real_text_layout(self):
        parser = _make_parser()
        summary_page = make_mock_page(SINOPAC_REAL_FIRST_PAGE_TEXT)
        txn_page = make_mock_page(SINOPAC_REAL_TXN_PAGE_TEXT)
        pages = cast(
            list[pdfplumber.page.Page],
            [summary_page, txn_page],
        )

        txns = parser._extract_transactions(pages, 2026)

        # Expect: negative refund + 3 consumption rows = 4 items
        assert len(txns) == 4
        # Refund row first in the sample text
        refund = txns[0]
        assert refund.amount == -7147
        assert refund.trans_date == date(2026, 3, 5)

        consumption_amounts = [t.amount for t in txns[1:]]
        assert 500 in consumption_amounts
        assert 975 in consumption_amounts
        assert 1188 in consumption_amounts

        txn_with_card = next(t for t in txns if t.amount == 500)
        assert txn_with_card.card_last4 == "4300"
        assert txn_with_card.merchant.startswith("悠遊卡")
