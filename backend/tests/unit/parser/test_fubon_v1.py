"""FubonV1Parser unit tests.

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
    FUBON_EXPECTED_BILLING_MONTH,
    FUBON_EXPECTED_DUE_DATE,
    FUBON_EXPECTED_TOTAL_AMOUNT,
    FUBON_FIRST_PAGE_TEXT,
    FUBON_NON_FUBON_PAGE_TEXT,
    FUBON_SUMMARY_MISSING_DUE_DATE_TEXT,
    FUBON_SUMMARY_MISSING_TOTAL_TEXT,
    FUBON_TABLE_HEADER_ROW,
    FUBON_TRANSACTION_ROWS,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate FubonV1Parser (deferred import)."""
    from ccas.parser.banks.fubon_v1 import FubonV1Parser

    return FubonV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_fubon_statement(self):
        parser = _make_parser()
        assert parser._identify(FUBON_FIRST_PAGE_TEXT) is True

    def test_rejects_non_fubon_statement(self):
        parser = _make_parser()
        assert parser._identify(FUBON_NON_FUBON_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("台北富邦 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(FUBON_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == FUBON_EXPECTED_BILLING_MONTH
        assert total_amount == FUBON_EXPECTED_TOTAL_AMOUNT
        assert due_date == FUBON_EXPECTED_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(FUBON_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(FUBON_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = (
            "台北富邦銀行 信用卡帳單\n繳費截止日：2026/04/15\n本期應繳總額：NT$ 100\n"
        )
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])

    def test_extracts_roc_billing_month_and_due_date(self):
        parser = _make_parser()
        text = (
            "台北富邦銀行 信用卡帳單\n"
            "115年03月份帳單\n"
            "繳費截止日：115/04/15\n"
            "本期應繳總額：NT$ 9,200\n"
        )
        page = make_mock_page(text)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == "2026-03"
        assert total_amount == 9200
        assert due_date == date(2026, 4, 15)


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [FUBON_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_from_table(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(FUBON_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 680
        assert txns[0].trans_date == date(2026, 3, 5)
        assert txns[0].posting_date == date(2026, 3, 7)
        assert txns[0].card_last4 == "8899"

    def test_handles_comma_in_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([FUBON_TRANSACTION_ROWS[2]])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 1250

    def test_returns_empty_for_no_tables(self):
        parser = _make_parser()
        page = make_mock_page("no table content")

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert txns == ()

    def test_skips_malformed_rows(self, caplog):
        parser = _make_parser()
        bad_row = ["03/01", "", "", "", "not-a-number"]
        pages = self._make_pages_with_table([bad_row])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 0
        assert "跳過" in caplog.text or "warning" in caplog.text.lower()

    def test_text_line_extraction(self):
        parser = _make_parser()
        text = "2026/03/05  2026/03/07  全聯福利中心  680\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].trans_date == date(2026, 3, 5)
        assert txns[0].posting_date == date(2026, 3, 7)
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 680

    def test_text_line_extraction_simple_format(self):
        parser = _make_parser()
        text = "2026/03/05  全聯福利中心  680\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].trans_date == date(2026, 3, 5)
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 680

    def test_simple_format_multi_page_all_captured(self):
        """Multi-page bill with simple-format text: all pages must be captured."""
        parser = _make_parser()
        page1 = make_mock_page("2026/03/05  全聯福利中心  680\n")
        page2 = make_mock_page("2026/03/10  台灣大哥大  499\n")

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]), 2026
        )

        assert len(txns) == 2
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 680
        assert txns[1].merchant == "台灣大哥大"
        assert txns[1].amount == 499


# -- can_parse tests --


class TestCanParse:
    def test_returns_true_for_fubon(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(FUBON_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_returns_false_for_non_fubon(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(FUBON_NON_FUBON_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is False

    def test_returns_false_on_corrupt_pdf(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "corrupt.pdf"

        with patch("pdfplumber.open", side_effect=Exception("corrupt")):
            assert parser.can_parse(pdf_path) is False

    def test_returns_false_for_empty_pdf(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "empty.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = []
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is False


# -- parse full flow test --


class TestParse:
    def test_returns_complete_parse_result(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        table = [FUBON_TABLE_HEADER_ROW, *FUBON_TRANSACTION_ROWS]
        mock_page = make_mock_page(FUBON_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "FUBON"
        assert result.billing_month == FUBON_EXPECTED_BILLING_MONTH
        assert result.total_amount == FUBON_EXPECTED_TOTAL_AMOUNT
        assert result.due_date == FUBON_EXPECTED_DUE_DATE
        assert len(result.transactions) == 3
