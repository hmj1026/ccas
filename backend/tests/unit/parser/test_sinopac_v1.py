"""SinopacV1Parser unit tests.

Tests internal methods (_identify, _extract_summary, _extract_transactions)
using text fixtures, not real PDFs.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock, patch

import pdfplumber.page
import pytest

from ccas.parser.banks.sinopac_v1 import (
    _is_refund_row,
    _is_transaction_table,
    _parse_date,
    _parse_mmdd,
    _parse_transaction_row,
)
from ccas.parser.base import ParseError

from .conftest import (
    EXPECTED_SINOPAC_BILLING_MONTH,
    EXPECTED_SINOPAC_DUE_DATE,
    EXPECTED_SINOPAC_EXTRA_COLUMN_TOTAL_AMOUNT,
    EXPECTED_SINOPAC_REAL_BILLING_MONTH,
    EXPECTED_SINOPAC_REAL_DUE_DATE,
    EXPECTED_SINOPAC_REAL_TOTAL_AMOUNT,
    EXPECTED_SINOPAC_TOTAL_AMOUNT,
    SINOPAC_EXTRA_COLUMN_FIRST_PAGE_TEXT,
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

        # 退款政策（R26）：退款列（永豐自扣 / 負數）保留為負數明細，而非丟棄。
        # 預期 3 筆消費 + 1 筆退款（-7147）；頁尾「本期應繳金額合計」摘要列仍排除。
        assert len(txns) == 4

        amounts = [t.amount for t in txns]
        assert 500 in amounts
        assert 975 in amounts
        assert 1188 in amounts
        # 退款保留為負數
        assert -7147 in amounts
        refund = next(t for t in txns if t.amount < 0)
        assert refund.merchant.startswith("永豐自扣")

        txn_with_card = next(t for t in txns if t.amount == 500)
        assert txn_with_card.card_last4 == "4300"
        assert txn_with_card.merchant.startswith("悠遊卡")

    def test_extra_column_summary_falls_back_to_keyword(self, caplog):
        """摘要列欄位數異動（8 欄）時拒用位置 group(6)，退化到 keyword 路徑。

        韌性修補：未來帳單版本插入欄位會使 group(6) 抓到錯誤金額；偵測到欄位
        數不符即 fallback 到 `本期應繳總額：NT$ ...` keyword，避免回報錯誤金額。
        """
        import logging

        parser = _make_parser()
        page = make_mock_page(SINOPAC_EXTRA_COLUMN_FIRST_PAGE_TEXT)

        with caplog.at_level(logging.WARNING):
            _, total_amount, _ = parser._extract_summary([page])

        assert total_amount == EXPECTED_SINOPAC_EXTRA_COLUMN_TOTAL_AMOUNT
        # 必須不是位置列 group(6)（12,579），證明沒被錯誤欄位污染。
        assert total_amount != 12579
        assert caplog.text  # 有 warning 記錄

    def test_cross_year_mmdd_real_text(self):
        """Jan statement with Dec transactions → previous calendar year.

        Regression: SINOPAC MM/DD paths always used billing_year, so a December
        transaction on a January statement was stamped with the wrong year.
        """
        parser = _make_parser()
        text = "12/28 12/30 跨年商店 120\n01/05 01/06 一月商店 80\n"
        page = make_mock_page(text)

        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026, 1
        )

        assert len(txns) == 2
        dec = next(t for t in txns if t.merchant == "跨年商店")
        assert dec.trans_date == date(2025, 12, 28)
        assert dec.posting_date == date(2025, 12, 30)
        jan = next(t for t in txns if t.merchant == "一月商店")
        assert jan.trans_date == date(2026, 1, 5)

    def test_parse_mmdd_cross_year_helper(self):
        """_parse_mmdd shifts year back when month exceeds billing month."""
        from ccas.parser.banks.sinopac_v1 import _parse_mmdd

        assert _parse_mmdd("12/28", 2026, 1) == date(2025, 12, 28)
        assert _parse_mmdd("01/05", 2026, 1) == date(2026, 1, 5)
        # Default (billing_month_num=0) keeps the legacy no-shift behaviour.
        assert _parse_mmdd("12/28", 2026) == date(2026, 12, 28)


# -- Helper-function unit tests (added for branch coverage) --


class TestParseDateHelper:
    """Direct tests of the module-level _parse_date helper."""

    def test_parses_mmdd(self):
        assert _parse_date("03/01", 2026) == date(2026, 3, 1)

    def test_mmdd_cross_year_shifts_back(self):
        assert _parse_date("12/28", 2026, 1) == date(2025, 12, 28)

    def test_parses_western_full_date(self):
        assert _parse_date("2026/03/01", 2026) == date(2026, 3, 1)

    def test_converts_roc_full_date(self):
        # 民國 115 + 1911 = 西元 2026
        assert _parse_date("115/03/01", 2026) == date(2026, 3, 1)

    def test_returns_none_for_wrong_part_count(self):
        assert _parse_date("2026", 2026) is None

    def test_returns_none_for_invalid_values(self):
        assert _parse_date("2026/13/45", 2026) is None
        assert _parse_date("xx/yy", 2026) is None


class TestParseMmddNoMatch:
    def test_returns_none_for_non_mmdd_string(self):
        assert _parse_mmdd("not-a-date", 2026) is None


class TestIsRefundRow:
    def test_negative_amount_is_refund(self):
        assert _is_refund_row("", "全聯福利中心", -100) is True

    def test_refund_line_prefix_is_refund(self):
        assert _is_refund_row("(-) 沖正 100", "某商店", 100) is True

    def test_refund_merchant_keyword_is_refund(self):
        assert _is_refund_row("", "退款－某商店", 100) is True

    def test_normal_row_is_not_refund(self):
        assert _is_refund_row("", "全聯福利中心", 100) is False


class TestCanParseEmptyPdf:
    def test_returns_false_for_pdf_without_pages(self, tmp_path):
        parser = _make_parser()
        pdf_path = tmp_path / "empty.pdf"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = []
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            assert parser.can_parse(pdf_path) is False


class TestRocSummaryHelpers:
    def test_extract_billing_month_roc_year(self):
        parser = _make_parser()
        assert parser._extract_billing_month("115年03月") == "2026-03"

    def test_extract_due_date_roc_year(self):
        parser = _make_parser()
        assert parser._extract_due_date("繳款截止日：115/03/27") == date(2026, 3, 27)


class TestIsTransactionTable:
    def test_empty_table_returns_false(self):
        assert _is_transaction_table([]) is False

    def test_real_header_keywords_match(self):
        # 入帳 + 臺幣金額 (production header) without the legacy 交易日 keyword.
        assert _is_transaction_table([["入帳日", "卡號末四碼", "臺幣金額"]]) is True


class TestExtractTransactionsSkipNonTxnTable:
    def test_skips_table_without_keywords(self):
        parser = _make_parser()
        page = make_mock_page("", tables=[[["欄位A", "欄位B"], ["1", "2"]]])
        txns = parser._extract_transactions(
            cast(list[pdfplumber.page.Page], [page]), 2026
        )
        assert txns == ()


class TestParseTransactionRow:
    def test_five_col_full_date_fallback(self):
        row: list[str | None] = ["2026/03/01", "2026/03/05", "5678", "商店", "100"]
        item = _parse_transaction_row(row, 2026)
        assert item is not None
        assert item.trans_date == date(2026, 3, 1)
        assert item.posting_date == date(2026, 3, 5)
        assert item.card_last4 == "5678"
        assert item.amount == 100

    def test_five_col_unparseable_date_returns_none(self):
        assert _parse_transaction_row(["xx/yy", "", "", "商店", "100"], 2026) is None

    def test_five_col_refund_merchant_negated(self):
        row: list[str | None] = ["03/01", "03/05", "5678", "退款－某商店", "100"]
        item = _parse_transaction_row(row, 2026)
        assert item is not None
        assert item.amount == -100

    def test_three_col_basic(self):
        item = _parse_transaction_row(["03/01", "商店", "100"], 2026)
        assert item is not None
        assert item.amount == 100
        assert item.trans_date == date(2026, 3, 1)
        assert item.posting_date is None

    def test_three_col_full_date_fallback(self):
        item = _parse_transaction_row(["2026/03/01", "商店", "100"], 2026)
        assert item is not None
        assert item.trans_date == date(2026, 3, 1)

    def test_three_col_unparseable_date_returns_none(self):
        assert _parse_transaction_row(["xx/yy", "商店", "100"], 2026) is None

    def test_three_col_refund_merchant_negated(self):
        item = _parse_transaction_row(["03/01", "退款－某店", "100"], 2026)
        assert item is not None
        assert item.amount == -100

    def test_too_few_columns_returns_none(self):
        assert _parse_transaction_row(["03/01", "100"], 2026) is None


class TestTextTransactionTiers:
    """Drive the legacy tier-2/tier-3 text fallbacks via _extract_transactions."""

    def _pages(self, text: str) -> list[pdfplumber.page.Page]:
        return cast(list[pdfplumber.page.Page], [make_mock_page(text)])

    def test_tier2_legacy_full_format(self):
        parser = _make_parser()
        text = (
            "2026/03/01 2026/03/05 商店一 100\n2026/03/02 2026/03/06 退款－商店二 50\n"
        )
        txns = parser._extract_transactions(self._pages(text), 2026)
        assert len(txns) == 2
        # 退款保留為負數明細（R26）。
        assert sorted(t.amount for t in txns) == [-50, 100]

    def test_tier2_invalid_date_skipped(self):
        parser = _make_parser()
        txns = parser._extract_transactions(
            self._pages("2026/13/45 2026/03/05 商店 100\n"), 2026
        )
        assert txns == ()

    def test_tier2_non_numeric_amount_skipped(self):
        parser = _make_parser()
        txns = parser._extract_transactions(
            self._pages("2026/03/01 2026/03/05 商店 ,\n"), 2026
        )
        assert txns == ()

    def test_tier3_simple_format(self):
        parser = _make_parser()
        text = "2026/03/01 商店一 100\n2026/03/02 退款－商店二 50\n"
        txns = parser._extract_transactions(self._pages(text), 2026)
        assert len(txns) == 2
        assert sorted(t.amount for t in txns) == [-50, 100]

    def test_tier3_invalid_date_skipped(self):
        parser = _make_parser()
        txns = parser._extract_transactions(self._pages("2026/13/45 商店 100\n"), 2026)
        assert txns == ()


class TestRealTextEdges:
    """Edge branches inside the tier-1 real MM/DD text parser."""

    def _pages(self, text: str) -> list[pdfplumber.page.Page]:
        return cast(list[pdfplumber.page.Page], [make_mock_page(text)])

    def test_trans_date_none_skipped(self):
        # group(1) "1/2" fails the strict 2-digit MM/DD regex → trans_date None.
        parser = _make_parser()
        txns = parser._extract_transactions(self._pages("1/2 1/2 商店 100\n"), 2026)
        assert txns == ()

    def test_summary_total_row_skipped(self):
        parser = _make_parser()
        text = "03/05 03/05 本期應繳金額合計 12,579\n03/06 03/06 小計 100\n"
        txns = parser._extract_transactions(self._pages(text), 2026)
        assert txns == ()

    def test_invalid_mmdd_value_caught(self):
        # group(1) "13/45" matches the regex but date() raises → swallowed.
        parser = _make_parser()
        txns = parser._extract_transactions(self._pages("13/45 03/05 商店 100\n"), 2026)
        assert txns == ()
