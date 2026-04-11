"""EsunV1Parser unit tests.

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
    ESUN_FIRST_PAGE_TEXT,
    ESUN_NON_ESUN_PAGE_TEXT,
    ESUN_REAL_PAGE0_TEXT,
    ESUN_REAL_PAGE1_TEXT,
    ESUN_REAL_PAGE2_TEXT,
    ESUN_SUMMARY_MISSING_DUE_DATE_TEXT,
    ESUN_SUMMARY_MISSING_TOTAL_TEXT,
    ESUN_TABLE_HEADER_ROW,
    ESUN_TRANSACTION_ROWS,
    EXPECTED_ESUN_BILLING_MONTH,
    EXPECTED_ESUN_DUE_DATE,
    EXPECTED_ESUN_REAL_BILLING_MONTH,
    EXPECTED_ESUN_REAL_DUE_DATE,
    EXPECTED_ESUN_REAL_TOTAL_AMOUNT,
    EXPECTED_ESUN_TOTAL_AMOUNT,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate EsunV1Parser (deferred import)."""
    from ccas.parser.banks.esun_v1 import EsunV1Parser

    return EsunV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_esun_statement(self):
        parser = _make_parser()
        assert parser._identify(ESUN_FIRST_PAGE_TEXT) is True

    def test_rejects_non_esun_statement(self):
        parser = _make_parser()
        assert parser._identify(ESUN_NON_ESUN_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("玉山銀行 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(ESUN_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_ESUN_BILLING_MONTH
        assert total_amount == EXPECTED_ESUN_TOTAL_AMOUNT
        assert due_date == EXPECTED_ESUN_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(ESUN_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(ESUN_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = "玉山銀行 信用卡帳單\n繳費截止日：2026/04/15\n本期應繳總額：NT$ 100\n"
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [ESUN_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(ESUN_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 350
        assert txns[0].trans_date == date(2026, 3, 1)
        assert txns[0].posting_date == date(2026, 3, 3)
        assert txns[0].card_last4 == "4567"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([ESUN_TRANSACTION_ROWS[1]])

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
        table1 = [ESUN_TABLE_HEADER_ROW, ESUN_TRANSACTION_ROWS[0]]
        table2 = [ESUN_TABLE_HEADER_ROW, ESUN_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2

    def test_3_column_table_fallback(self):
        """Minimal 3-column table: trans_date, merchant, amount."""
        parser = _make_parser()
        header = ["交易日", "交易說明", "金額"]
        rows = [["03/01", "全家便利商店", "350"]]
        table = [header, *rows]
        page = make_mock_page("", tables=[table])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 350
        assert txns[0].posting_date is None
        assert txns[0].card_last4 is None

    def test_text_line_extraction_fallback(self):
        """When no tables exist, fall back to text line parsing."""
        parser = _make_parser()
        text = (
            "交易明細\n"
            "2026/03/01  2026/03/03  全家便利商店  350\n"
            "2026/03/08  2026/03/10  蝦皮購物  1280\n"
        )
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 2
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 350
        assert txns[0].posting_date == date(2026, 3, 3)

    def test_simple_text_line_extraction(self):
        """Simple format: date merchant amount (no posting date)."""
        parser = _make_parser()
        text = "2026/03/01  全家便利商店  350\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].posting_date is None


# -- ROC date support tests --


class TestRocDateSupport:
    def test_roc_billing_month(self):
        parser = _make_parser()
        text = (
            "玉山銀行 信用卡帳單\n"
            "115年03月份帳單\n"
            "繳費截止日：2026/04/15\n"
            "本期應繳總額：NT$ 100\n"
        )
        page = make_mock_page(text)

        billing_month, _, _ = parser._extract_summary([page])

        assert billing_month == "2026-03"

    def test_roc_due_date(self):
        parser = _make_parser()
        text = (
            "玉山銀行 信用卡帳單\n"
            "2026年03月份帳單\n"
            "繳費截止日：115/04/15\n"
            "本期應繳總額：NT$ 100\n"
        )
        page = make_mock_page(text)

        _, _, due_date = parser._extract_summary([page])

        assert due_date == date(2026, 4, 15)


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_esun(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(ESUN_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_esun(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(ESUN_NON_ESUN_PAGE_TEXT)
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

        table = [ESUN_TABLE_HEADER_ROW, *ESUN_TRANSACTION_ROWS]
        mock_page = make_mock_page(ESUN_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "ESUN"
        assert result.billing_month == EXPECTED_ESUN_BILLING_MONTH
        assert result.total_amount == EXPECTED_ESUN_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_ESUN_DUE_DATE
        assert len(result.transactions) == 3


# -- Real PDF format tests (ROC year + TWD prefix + multi-page identify) --


class TestRealPdfFormat:
    def test_identify_spans_all_pages(self):
        parser = _make_parser()
        # page 0 lacks "玉山銀行"; only last page has it
        combined = ESUN_REAL_PAGE0_TEXT + "\n" + ESUN_REAL_PAGE2_TEXT
        assert parser._identify(combined) is True

    def test_identify_rejects_without_keywords(self):
        parser = _make_parser()
        assert parser._identify("無關文字") is False

    def test_extract_summary_roc_year_no_label(self):
        parser = _make_parser()
        page0 = make_mock_page(ESUN_REAL_PAGE0_TEXT)
        page1 = make_mock_page(ESUN_REAL_PAGE1_TEXT)
        page2 = make_mock_page(ESUN_REAL_PAGE2_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary(
            cast(list[pdfplumber.page.Page], [page0, page1, page2])
        )

        assert billing_month == EXPECTED_ESUN_REAL_BILLING_MONTH
        assert total_amount == EXPECTED_ESUN_REAL_TOTAL_AMOUNT
        assert due_date == EXPECTED_ESUN_REAL_DUE_DATE

    def test_extract_transactions_real_format(self):
        parser = _make_parser()
        page0 = make_mock_page(ESUN_REAL_PAGE0_TEXT)
        page1 = make_mock_page(ESUN_REAL_PAGE1_TEXT)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page0, page1]),
            2026,
        )

        # Expect: refund -10615 + 2 consumption rows = 3 items
        assert len(txns) == 3
        refund = next(t for t in txns if t.amount == -10615)
        assert refund.trans_date == date(2026, 3, 9)

        consumption_142 = next(t for t in txns if t.amount == 142)
        assert consumption_142.trans_date == date(2026, 2, 12)
        assert consumption_142.posting_date == date(2026, 2, 23)
        assert "新光三越" in consumption_142.merchant
