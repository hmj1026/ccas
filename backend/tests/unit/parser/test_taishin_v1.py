"""TaishinV1Parser unit tests.

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
    EXPECTED_TAISHIN_BILLING_MONTH,
    EXPECTED_TAISHIN_DUE_DATE,
    EXPECTED_TAISHIN_REAL_BILLING_MONTH,
    EXPECTED_TAISHIN_REAL_DUE_DATE,
    EXPECTED_TAISHIN_REAL_TOTAL_AMOUNT,
    EXPECTED_TAISHIN_TOTAL_AMOUNT,
    TAISHIN_FIRST_PAGE_TEXT,
    TAISHIN_NON_TAISHIN_PAGE_TEXT,
    TAISHIN_REAL_SUMMARY_TEXT,
    TAISHIN_REAL_TRANSACTIONS_TEXT,
    TAISHIN_SUMMARY_MISSING_DUE_DATE_TEXT,
    TAISHIN_SUMMARY_MISSING_TOTAL_TEXT,
    TAISHIN_TABLE_HEADER_ROW,
    TAISHIN_TRANSACTION_ROWS,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate TaishinV1Parser (deferred import)."""
    from ccas.parser.banks.taishin_v1 import TaishinV1Parser

    return TaishinV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_taishin_statement(self):
        parser = _make_parser()
        assert parser._identify(TAISHIN_FIRST_PAGE_TEXT) is True

    def test_rejects_non_taishin_statement(self):
        parser = _make_parser()
        assert parser._identify(TAISHIN_NON_TAISHIN_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("台新銀行 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(TAISHIN_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_TAISHIN_BILLING_MONTH
        assert total_amount == EXPECTED_TAISHIN_TOTAL_AMOUNT
        assert due_date == EXPECTED_TAISHIN_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(TAISHIN_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(TAISHIN_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = "台新銀行 信用卡帳單\n繳費截止日：2026/04/22\n本期應繳總額：NT$ 100\n"
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [TAISHIN_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(TAISHIN_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 520
        assert txns[0].trans_date == date(2026, 3, 3)
        assert txns[0].posting_date == date(2026, 3, 5)
        assert txns[0].card_last4 == "6789"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([TAISHIN_TRANSACTION_ROWS[1]])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 2360

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
        table1 = [TAISHIN_TABLE_HEADER_ROW, TAISHIN_TRANSACTION_ROWS[0]]
        table2 = [TAISHIN_TABLE_HEADER_ROW, TAISHIN_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_taishin(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(TAISHIN_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_taishin(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(TAISHIN_NON_TAISHIN_PAGE_TEXT)
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

        table = [TAISHIN_TABLE_HEADER_ROW, *TAISHIN_TRANSACTION_ROWS]
        mock_page = make_mock_page(TAISHIN_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "TAISHIN"
        assert result.billing_month == EXPECTED_TAISHIN_BILLING_MONTH
        assert result.total_amount == EXPECTED_TAISHIN_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_TAISHIN_DUE_DATE
        assert len(result.transactions) == 3


# -- Real-format PDF tests (ROC year, text-based layout) --


class TestRealPdfFormat:
    def test_extracts_due_date_with_space_separator(self):
        parser = _make_parser()
        text = "帳務資訊\n繳款截止日 113/11/27\n"
        assert parser._extract_due_date(text) == date(2024, 11, 27)

    def test_extracts_due_date_with_colon(self):
        parser = _make_parser()
        text = "繳款截止日：113/11/27\n"
        assert parser._extract_due_date(text) == date(2024, 11, 27)

    def test_extracts_real_summary(self):
        parser = _make_parser()
        page = make_mock_page(TAISHIN_REAL_SUMMARY_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_TAISHIN_REAL_BILLING_MONTH
        assert total_amount == EXPECTED_TAISHIN_REAL_TOTAL_AMOUNT
        assert due_date == EXPECTED_TAISHIN_REAL_DUE_DATE

    def test_total_amount_prefers_cumulative_over_previous(self):
        """Guard: must match 本期累計應繳金額, not 上期應繳總額."""
        parser = _make_parser()
        page = make_mock_page(TAISHIN_REAL_SUMMARY_TEXT)

        _, total_amount, _ = parser._extract_summary([page])

        # 上期應繳總額 is 43,642; 本期累計應繳金額 is 35,366
        assert total_amount == 35366
        assert total_amount != 43642

    def test_extracts_roc_text_transactions(self):
        parser = _make_parser()
        page = make_mock_page(TAISHIN_REAL_TRANSACTIONS_TEXT)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]),
            2020,
        )

        # Expect: payment, instalment, gas, service fee, foreign, refund, apple
        assert len(txns) >= 6
        merchants = [t.merchant for t in txns]
        amounts = [t.amount for t in txns]
        # Payment line
        assert any("付款已收到" in m for m in merchants)
        assert -18901 in amounts
        # Instalment with TW country code
        assert any("ＰＣＨＯＭＥ" in m for m in merchants)
        assert 993 in amounts
        # Foreign transaction (FX trailing info should be stripped)
        assert any("ProDirectSoccer" in m for m in merchants)
        assert 3496 in amounts
        # Refund
        assert -2 in amounts

    def test_roc_transaction_uses_trans_date_year(self):
        parser = _make_parser()
        page = make_mock_page("108/12/27 108/12/27 您的付款已收到，謝謝您！ -18,901\n")

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]),
            2020,
        )

        assert len(txns) == 1
        # ROC 108 + 1911 = 2019
        assert txns[0].trans_date == date(2019, 12, 27)
        assert txns[0].amount == -18901

    def test_tracks_card_last4_from_header(self):
        parser = _make_parser()
        text = (
            "ａＧｏＧｏ iCash 御璽卡 王小明 (卡號末四碼:1234)\n"
            "108/12/13 108/12/18 全國加油站文心站 TAICHU 800 TW\n"
        )
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]),
            2020,
        )

        assert len(txns) == 1
        assert txns[0].card_last4 == "1234"
