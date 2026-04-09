"""UbotV1Parser unit tests.

Tests internal methods (_identify, _extract_summary, _extract_transactions)
using text fixtures, not real PDFs.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock, patch

import pdfplumber.page
import pytest
from pdfplumber.utils.exceptions import PdfminerException

from ccas.parser.banks.ubot_v1 import _parse_date, _parse_mmdd
from ccas.parser.base import ParseError

from .conftest import (
    EXPECTED_UBOT_BILLING_MONTH,
    EXPECTED_UBOT_DUE_DATE,
    EXPECTED_UBOT_TOTAL_AMOUNT,
    UBOT_FIRST_PAGE_TEXT,
    UBOT_NON_UBOT_PAGE_TEXT,
    UBOT_SUMMARY_MISSING_DUE_DATE_TEXT,
    UBOT_SUMMARY_MISSING_TOTAL_TEXT,
    UBOT_TABLE_HEADER_ROW,
    UBOT_TRANSACTION_ROWS,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate UbotV1Parser (deferred import)."""
    from ccas.parser.banks.ubot_v1 import UbotV1Parser

    return UbotV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_ubot_statement(self):
        parser = _make_parser()
        assert parser._identify(UBOT_FIRST_PAGE_TEXT) is True

    def test_rejects_non_ubot_statement(self):
        parser = _make_parser()
        assert parser._identify(UBOT_NON_UBOT_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("聯邦銀行 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(UBOT_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_UBOT_BILLING_MONTH
        assert total_amount == EXPECTED_UBOT_TOTAL_AMOUNT
        assert due_date == EXPECTED_UBOT_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(UBOT_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(UBOT_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = "聯邦銀行 信用卡帳單\n繳費截止日：2026/04/18\n本期應繳總額：NT$ 100\n"
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [UBOT_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(UBOT_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "7-ELEVEN"
        assert txns[0].amount == 120
        assert txns[0].trans_date == date(2026, 3, 5)
        assert txns[0].posting_date == date(2026, 3, 7)
        assert txns[0].card_last4 == "3456"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([UBOT_TRANSACTION_ROWS[1]])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 1850

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
        assert "Skipping" in caplog.text or "warning" in caplog.text.lower()

    def test_multi_page_transactions(self):
        parser = _make_parser()
        table1 = [UBOT_TABLE_HEADER_ROW, UBOT_TRANSACTION_ROWS[0]]
        table2 = [UBOT_TABLE_HEADER_ROW, UBOT_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2

    def test_3_column_table_fallback(self):
        parser = _make_parser()
        header = ["交易日", "交易說明", "金額"]
        rows = [["03/05", "7-ELEVEN", "120"]]
        table = [header, *rows]
        page = make_mock_page("", tables=[table])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].merchant == "7-ELEVEN"
        assert txns[0].amount == 120
        assert txns[0].posting_date is None
        assert txns[0].card_last4 is None

    def test_text_line_extraction_fallback(self):
        parser = _make_parser()
        text = (
            "交易明細\n"
            "2026/03/05 2026/03/07 7-ELEVEN 120\n"
            "2026/03/12 2026/03/14 全聯福利中心 1850\n"
        )
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 2
        assert txns[0].merchant == "7-ELEVEN"
        assert txns[0].amount == 120
        assert txns[0].posting_date == date(2026, 3, 7)

    def test_simple_text_line_extraction(self):
        parser = _make_parser()
        text = "2026/03/05 7-ELEVEN 120\n2026/03/12 全聯福利中心 1850\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 2
        assert txns[0].merchant == "7-ELEVEN"
        assert txns[0].posting_date is None

    def test_skips_non_transaction_table(self):
        parser = _make_parser()
        non_txn_table = [["帳戶資訊", "值"], ["帳號", "1234567890"]]
        page = make_mock_page("", tables=[non_txn_table])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert txns == ()


# -- _parse_date / _parse_mmdd tests --


class TestParseDate:
    def test_western_date(self):
        assert _parse_date("2026/03/05", 2026) == date(2026, 3, 5)

    def test_roc_date(self):
        assert _parse_date("115/03/05", 2026) == date(2026, 3, 5)

    def test_mmdd_two_parts(self):
        assert _parse_date("03/05", 2026) == date(2026, 3, 5)

    def test_invalid_returns_none(self):
        assert _parse_date("abc", 2026) is None

    def test_single_part_returns_none(self):
        assert _parse_date("2026", 2026) is None

    def test_invalid_date_values_returns_none(self):
        assert _parse_date("2026/13/40", 2026) is None


class TestParseMmdd:
    def test_valid_mmdd(self):
        assert _parse_mmdd("03/05", 2026) == date(2026, 3, 5)

    def test_invalid_format_returns_none(self):
        assert _parse_mmdd("2026/03/05", 2026) is None

    def test_non_date_returns_none(self):
        assert _parse_mmdd("abc", 2026) is None


# -- ROC date format tests --


class TestRocDateSupport:
    def test_roc_billing_month(self):
        parser = _make_parser()
        text = (
            "聯邦銀行 信用卡帳單\n"
            "115年03月份帳單\n"
            "繳費截止日：2026/04/18\n"
            "本期應繳總額：NT$ 6,530\n"
        )
        page = make_mock_page(text)

        billing_month, _, _ = parser._extract_summary([page])

        assert billing_month == "2026-03"

    def test_roc_due_date(self):
        parser = _make_parser()
        text = (
            "聯邦銀行 信用卡帳單\n"
            "2026年03月份帳單\n"
            "繳費截止日：115/04/18\n"
            "本期應繳總額：NT$ 6,530\n"
        )
        page = make_mock_page(text)

        _, _, due_date = parser._extract_summary([page])

        assert due_date == date(2026, 4, 18)


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_ubot(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(UBOT_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_ubot(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(UBOT_NON_UBOT_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is False

    def test_can_parse_returns_false_on_corrupt_pdf(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "corrupt.pdf"

        with patch(
            "pdfplumber.open",
            side_effect=PdfminerException("corrupt"),
        ):
            assert parser.can_parse(pdf_path) is False

    def test_can_parse_returns_false_on_file_not_found(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "missing.pdf"

        with patch("pdfplumber.open", side_effect=FileNotFoundError("missing")):
            assert parser.can_parse(pdf_path) is False

    def test_can_parse_returns_false_for_empty_pages(self, tmp_path):
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
    def test_parse_returns_complete_result(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        table = [UBOT_TABLE_HEADER_ROW, *UBOT_TRANSACTION_ROWS]
        mock_page = make_mock_page(UBOT_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "UBOT"
        assert result.billing_month == EXPECTED_UBOT_BILLING_MONTH
        assert result.total_amount == EXPECTED_UBOT_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_UBOT_DUE_DATE
        assert len(result.transactions) == 3
