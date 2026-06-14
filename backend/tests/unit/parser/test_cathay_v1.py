"""CathayV1Parser unit tests.

Tests internal methods (_identify, _extract_summary, _extract_transactions)
using text fixtures, not real PDFs.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock, patch

import pdfplumber.page
import pytest

from ccas.parser.banks.cathay_v1 import _extract_transactions_text
from ccas.parser.base import ParseError

from .conftest import (
    CATHAY_FIRST_PAGE_TEXT,
    CATHAY_NON_CATHAY_PAGE_TEXT,
    CATHAY_REAL_ANCIENT_TEXT,
    CATHAY_REAL_GRID_TEXT,
    CATHAY_REAL_NEW_TEXT,
    CATHAY_REAL_OLD_TEXT,
    CATHAY_SUMMARY_MISSING_DUE_DATE_TEXT,
    CATHAY_SUMMARY_MISSING_TOTAL_TEXT,
    CATHAY_TABLE_HEADER_ROW,
    CATHAY_TRANSACTION_ROWS,
    EXPECTED_CATHAY_BILLING_MONTH,
    EXPECTED_CATHAY_DUE_DATE,
    EXPECTED_CATHAY_REAL_ANCIENT_DUE,
    EXPECTED_CATHAY_REAL_ANCIENT_MONTH,
    EXPECTED_CATHAY_REAL_ANCIENT_TOTAL,
    EXPECTED_CATHAY_REAL_GRID_DUE,
    EXPECTED_CATHAY_REAL_GRID_MONTH,
    EXPECTED_CATHAY_REAL_GRID_TOTAL,
    EXPECTED_CATHAY_REAL_NEW_DUE,
    EXPECTED_CATHAY_REAL_NEW_MONTH,
    EXPECTED_CATHAY_REAL_NEW_TOTAL,
    EXPECTED_CATHAY_REAL_OLD_DUE,
    EXPECTED_CATHAY_REAL_OLD_MONTH,
    EXPECTED_CATHAY_REAL_OLD_TOTAL,
    EXPECTED_CATHAY_TOTAL_AMOUNT,
    make_mock_page,
)


def _make_parser():
    """Import and instantiate CathayV1Parser (deferred import)."""
    from ccas.parser.banks.cathay_v1 import CathayV1Parser

    return CathayV1Parser()


# -- _identify tests --


class TestIdentify:
    def test_identifies_cathay_statement(self):
        parser = _make_parser()
        assert parser._identify(CATHAY_FIRST_PAGE_TEXT) is True

    def test_rejects_non_cathay_statement(self):
        parser = _make_parser()
        assert parser._identify(CATHAY_NON_CATHAY_PAGE_TEXT) is False

    def test_rejects_empty_text(self):
        parser = _make_parser()
        assert parser._identify("") is False

    def test_rejects_partial_match(self):
        parser = _make_parser()
        assert parser._identify("國泰世華 一般服務") is False


# -- _extract_summary tests --


class TestExtractSummary:
    def test_extracts_billing_month_total_due_date(self):
        parser = _make_parser()
        page = make_mock_page(CATHAY_FIRST_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == EXPECTED_CATHAY_BILLING_MONTH
        assert total_amount == EXPECTED_CATHAY_TOTAL_AMOUNT
        assert due_date == EXPECTED_CATHAY_DUE_DATE

    def test_raises_on_missing_due_date(self):
        parser = _make_parser()
        page = make_mock_page(CATHAY_SUMMARY_MISSING_DUE_DATE_TEXT)

        with pytest.raises(ParseError, match="繳費截止日"):
            parser._extract_summary([page])

    def test_raises_on_missing_total_amount(self):
        parser = _make_parser()
        page = make_mock_page(CATHAY_SUMMARY_MISSING_TOTAL_TEXT)

        with pytest.raises(ParseError, match="應繳總額"):
            parser._extract_summary([page])

    def test_raises_on_missing_billing_month(self):
        parser = _make_parser()
        text = (
            "國泰世華銀行 信用卡帳單\n繳費截止日：2026/04/12\n本期應繳總額：NT$ 100\n"
        )
        page = make_mock_page(text)

        with pytest.raises(ParseError, match="帳單月份"):
            parser._extract_summary([page])

    def test_extracts_roc_billing_month_and_due_date(self):
        parser = _make_parser()
        text = (
            "國泰世華銀行 信用卡帳單\n"
            "115年03月份帳單\n"
            "繳費截止日：115/04/12\n"
            "本期應繳總額：NT$ 9,200\n"
        )
        page = make_mock_page(text)

        billing_month, total_amount, due_date = parser._extract_summary([page])

        assert billing_month == "2026-03"
        assert total_amount == 9200
        assert due_date == date(2026, 4, 12)


# -- _extract_transactions tests --


class TestExtractTransactions:
    def _make_pages_with_table(
        self, rows: list[list[str]]
    ) -> list[pdfplumber.page.Page]:
        table = [CATHAY_TABLE_HEADER_ROW, *rows]
        page = make_mock_page("", tables=[table])
        return cast(list[pdfplumber.page.Page], [page])

    def test_extracts_basic_transactions(self):
        parser = _make_parser()
        pages = self._make_pages_with_table(CATHAY_TRANSACTION_ROWS)

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 3
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 180
        assert txns[0].trans_date == date(2026, 3, 2)
        assert txns[0].posting_date == date(2026, 3, 4)
        assert txns[0].card_last4 == "2345"

    def test_extracts_transaction_with_comma_amount(self):
        parser = _make_parser()
        pages = self._make_pages_with_table([CATHAY_TRANSACTION_ROWS[1]])

        txns = parser._extract_transactions(pages, 2026)

        assert len(txns) == 1
        assert txns[0].amount == 1450

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
        table1 = [CATHAY_TABLE_HEADER_ROW, CATHAY_TRANSACTION_ROWS[0]]
        table2 = [CATHAY_TABLE_HEADER_ROW, CATHAY_TRANSACTION_ROWS[1]]
        page1 = make_mock_page("", tables=[table1])
        page2 = make_mock_page("", tables=[table2])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page1, page2]),
            2026,
        )

        assert len(txns) == 2

    def test_extracts_three_column_table(self):
        parser = _make_parser()
        header = ["交易日", "交易說明", "金額"]
        rows = [["03/02", "全家便利商店", "180"]]
        table = [header, *rows]
        page = make_mock_page("", tables=[table])

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 180
        assert txns[0].posting_date is None
        assert txns[0].card_last4 is None

    def test_text_line_extraction_full_format(self):
        parser = _make_parser()
        text = "2026/03/02  2026/03/04  全家便利商店  180\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].trans_date == date(2026, 3, 2)
        assert txns[0].posting_date == date(2026, 3, 4)
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 180

    def test_text_line_extraction_simple_format(self):
        parser = _make_parser()
        text = "2026/03/02  全家便利商店  180\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )

        assert len(txns) == 1
        assert txns[0].trans_date == date(2026, 3, 2)
        assert txns[0].merchant == "全家便利商店"
        assert txns[0].amount == 180


# -- can_parse tests --


class TestCanParse:
    def test_can_parse_returns_true_for_cathay(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(CATHAY_FIRST_PAGE_TEXT)
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is True

    def test_can_parse_returns_false_for_non_cathay(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "test.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = make_mock_page(CATHAY_NON_CATHAY_PAGE_TEXT)
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

    def test_can_parse_returns_false_for_empty_pdf(self, tmp_path):
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

        table = [CATHAY_TABLE_HEADER_ROW, *CATHAY_TRANSACTION_ROWS]
        mock_page = make_mock_page(CATHAY_FIRST_PAGE_TEXT, tables=[table])

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = parser.parse(pdf_path)

        assert result.bank_code == "CATHAY"
        assert result.billing_month == EXPECTED_CATHAY_BILLING_MONTH
        assert result.total_amount == EXPECTED_CATHAY_TOTAL_AMOUNT
        assert result.due_date == EXPECTED_CATHAY_DUE_DATE
        assert len(result.transactions) == 3


# -- Real PDF format tests --


class TestRealPdfFormat:
    """真實國泰世華 PDF 文字佈局覆蓋（108、112 grid、115 header、106 ancient）。"""

    def _mock_pages(self, text: str) -> list[pdfplumber.page.Page]:
        return [cast(pdfplumber.page.Page, make_mock_page(text))]

    def test_can_parse_scans_all_pages_for_keyword(self):
        """page 0 被 CID 遮蔽，但 page 1 含關鍵字時 can_parse 回傳 True。"""
        parser = _make_parser()
        page0 = make_mock_page("VZ000013-TW-03/18 1/3\n王小明 先生\n")
        page1 = make_mock_page("國泰世華\n信用卡\n")
        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = [page0, page1]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf
            assert parser.can_parse("fake.pdf") is True  # type: ignore[arg-type]

    def test_identify_fallback_keyword_duoli(self):
        """Ancient PDF 無「國泰」字串但有「多利金」也應辨識為 CATHAY。"""
        parser = _make_parser()
        assert parser._identify("COSTCO多利金 0 28 0 0 28\n信用卡消費明細\n") is True

    def test_extract_summary_old_format_108(self):
        parser = _make_parser()
        month, total, due = parser._extract_summary(
            self._mock_pages(CATHAY_REAL_OLD_TEXT)
        )
        assert month == EXPECTED_CATHAY_REAL_OLD_MONTH
        assert total == EXPECTED_CATHAY_REAL_OLD_TOTAL
        assert due == EXPECTED_CATHAY_REAL_OLD_DUE

    def test_extract_summary_grid_format_112(self):
        parser = _make_parser()
        month, total, due = parser._extract_summary(
            self._mock_pages(CATHAY_REAL_GRID_TEXT)
        )
        assert month == EXPECTED_CATHAY_REAL_GRID_MONTH
        assert total == EXPECTED_CATHAY_REAL_GRID_TOTAL
        assert due == EXPECTED_CATHAY_REAL_GRID_DUE

    def test_extract_summary_new_header_115(self):
        parser = _make_parser()
        month, total, due = parser._extract_summary(
            self._mock_pages(CATHAY_REAL_NEW_TEXT)
        )
        assert month == EXPECTED_CATHAY_REAL_NEW_MONTH
        assert total == EXPECTED_CATHAY_REAL_NEW_TOTAL
        assert due == EXPECTED_CATHAY_REAL_NEW_DUE

    def test_extract_summary_ancient_106(self):
        parser = _make_parser()
        month, total, due = parser._extract_summary(
            self._mock_pages(CATHAY_REAL_ANCIENT_TEXT)
        )
        assert month == EXPECTED_CATHAY_REAL_ANCIENT_MONTH
        assert total == EXPECTED_CATHAY_REAL_ANCIENT_TOTAL
        assert due == EXPECTED_CATHAY_REAL_ANCIENT_DUE


class TestExtractTransactionsTextMultiPage:
    """R12：text fallback 守衛須在頁迴圈外，避免多頁帳單漏算交易。"""

    def test_simple_format_collected_across_all_pages(self):
        """兩頁皆 simple-format：兩頁交易都要被收集（舊碼只會收到第 1 頁）。"""
        page1 = make_mock_page("2026/03/05 星巴克 150\n")
        page2 = make_mock_page("2026/03/18 誠品書店 980\n")
        items = _extract_transactions_text([page1, page2], 2026)
        merchants = {i.merchant for i in items}
        assert len(items) == 2
        assert "星巴克" in merchants
        assert "誠品書店" in merchants

    def test_full_format_match_suppresses_simple_fallback(self):
        """有任一頁命中 full-format 時，simple fallback 不應再啟動（避免重複/雜訊）。"""
        page1 = make_mock_page("2026/03/05 2026/03/07 誠品書店 980\n")
        page2 = make_mock_page("2026/03/18 星巴克 150\n")
        items = _extract_transactions_text([page1, page2], 2026)
        assert len(items) == 1
        assert items[0].merchant == "誠品書店"
