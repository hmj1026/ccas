"""CtbcV1Parser unit tests.

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
    CTBC_FIRST_PAGE_TEXT,
    CTBC_INSTALLMENT_ROW,
    CTBC_NON_CTBC_PAGE_TEXT,
    CTBC_ROC_FIRST_PAGE_TEXT,
    CTBC_ROC_PAYMENT_PAGE_TEXT,
    CTBC_ROC_TXN_PAGE_TEXT,
    CTBC_SUMMARY_MISSING_DUE_DATE_TEXT,
    CTBC_SUMMARY_MISSING_TOTAL_TEXT,
    CTBC_TABLE_HEADER_ROW,
    CTBC_TRANSACTION_ROWS,
    EXPECTED_BILLING_MONTH,
    EXPECTED_DUE_DATE,
    EXPECTED_ROC_BILLING_MONTH,
    EXPECTED_ROC_DUE_DATE,
    EXPECTED_ROC_TOTAL_AMOUNT,
    EXPECTED_TOTAL_AMOUNT,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate CtbcV1Parser (deferred import)."""
    from ccas.parser.banks.ctbc_v1 import CtbcV1Parser

    return CtbcV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_ctbc_statement(self):
        parser = _make_parser()
        assert parser._identify(CTBC_FIRST_PAGE_TEXT) is True

    def test_rejects_non_ctbc_statement(self):
        parser = _make_parser()
        assert parser._identify(CTBC_NON_CTBC_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("中國信託 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(CTBC_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_BILLING_MONTH
        assert total_amount == EXPECTED_TOTAL_AMOUNT
        assert due_date == EXPECTED_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(CTBC_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(CTBC_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [CTBC_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(CTBC_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 350
        assert txns[0].trans_date == date(2026, 3, 1)
        assert txns[0].posting_date == date(2026, 3, 3)
        assert txns[0].card_last4 == "1234"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([CTBC_INSTALLMENT_ROW])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 1250

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
        table1 = [CTBC_TABLE_HEADER_ROW, CTBC_TRANSACTION_ROWS[0]]
        table2 = [CTBC_TABLE_HEADER_ROW, CTBC_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_ctbc(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(CTBC_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_ctbc(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(CTBC_NON_CTBC_PAGE_TEXT)
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

        table = [CTBC_TABLE_HEADER_ROW, *CTBC_TRANSACTION_ROWS]
        mock_page = make_mock_page(CTBC_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "CTBC"
        assert result.billing_month == EXPECTED_BILLING_MONTH
        assert result.total_amount == EXPECTED_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_DUE_DATE
        assert len(result.transactions) == 3


# -- ROC format tests (real CTBC PDFs) --


class TestIdentifyRoc:
    def test_identifies_by_url_and_roc_header(self):
        parser = _make_parser()
        assert parser._identify(CTBC_ROC_FIRST_PAGE_TEXT) is True

    def test_rejects_url_only_without_roc_header(self):
        parser = _make_parser()
        assert parser._identify("some text https://ctbc.tw/link") is False

    def test_rejects_roc_header_without_url(self):
        parser = _make_parser()
        assert parser._identify("115 03 1 / 3\nsome text") is False


class TestExtractSummaryRoc:
    def test_extracts_roc_billing_month(self):
        parser = _make_parser()
        page1 = make_mock_page(CTBC_ROC_FIRST_PAGE_TEXT)
        page3 = make_mock_page(CTBC_ROC_PAYMENT_PAGE_TEXT)

        billing_month, total, due = parser._extract_summary([page1, page3])

        assert billing_month == EXPECTED_ROC_BILLING_MONTH

    def test_extracts_roc_total_amount_from_payment_page(self):
        parser = _make_parser()
        page1 = make_mock_page(CTBC_ROC_FIRST_PAGE_TEXT)
        page3 = make_mock_page(CTBC_ROC_PAYMENT_PAGE_TEXT)

        _, total, _ = parser._extract_summary([page1, page3])

        assert total == EXPECTED_ROC_TOTAL_AMOUNT

    def test_extracts_roc_due_date_from_payment_page(self):
        parser = _make_parser()
        page1 = make_mock_page(CTBC_ROC_FIRST_PAGE_TEXT)
        page3 = make_mock_page(CTBC_ROC_PAYMENT_PAGE_TEXT)

        _, _, due = parser._extract_summary([page1, page3])

        assert due == EXPECTED_ROC_DUE_DATE


class TestExtractTransactionsRoc:
    def test_extracts_roc_transactions(self):
        parser = _make_parser()
        page = make_mock_page(CTBC_ROC_TXN_PAGE_TEXT)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 4
        assert txns[0].trans_date == date(2026, 2, 9)
        assert txns[0].posting_date == date(2026, 2, 11)
        assert txns[0].amount == 28
        assert txns[0].card_last4 == "6713"
        assert txns[0].merchant == ""

    def test_skips_non_transaction_lines(self):
        """Summary and payment lines should not match transaction regex."""
        parser = _make_parser()
        text = "115/03/10 3,292 2,967 0 3,292 0 +2,967\n115/03/02 -3,292\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 0

    def test_malformed_roc_transaction_skipped(self, caplog):
        """ROC transaction with invalid date should be skipped."""
        parser = _make_parser()
        text = "999/99/99 999/99/99 100 1234 TW\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 0
