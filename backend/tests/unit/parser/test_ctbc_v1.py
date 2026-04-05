"""CtbcV1Parser unit tests.

Tests internal methods (_identify, _extract_summary, _extract_transactions)
using text fixtures, not real PDFs.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock, patch

import pdfplumber.page
import pytest

from ccas.parser.banks.ctbc_v1 import _is_non_transaction_merchant
from ccas.parser.base import ParseError

from .conftest import (
    CTBC_FIRST_PAGE_TEXT,
    CTBC_GARBLED_TEXT,
    CTBC_INSTALLMENT_ROW,
    CTBC_NON_CTBC_PAGE_TEXT,
    CTBC_ROC_FIRST_PAGE_TEXT,
    CTBC_ROC_PAYMENT_PAGE_TEXT,
    CTBC_ROC_TXN_PAGE_TEXT,
    CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT,
    CTBC_ROC_ZERO_BALANCE_TXN_PAGE_TEXT,
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

    def test_accepts_roc_header_without_url(self):
        """Older CTBC PDFs (ROC 106-110) have ROC header but no ctbc.tw URL."""
        parser = _make_parser()
        assert parser._identify("115 03 1 / 3\nsome text") is True


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

    def test_filters_non_transaction_merchant(self):
        """Transactions with known header merchant names are filtered out."""
        parser = _make_parser()
        text = "115/02/09 115/02/11 28 6713 TW\n115/02/12 115/02/23 75 6713 TW\n"
        page = make_mock_page(text)

        merchants = iter(["消費暨收費摘要表", "全聯福利中心"])
        with patch(
            "ccas.parser.banks.ctbc_v1._match_merchant_to_transaction",
            side_effect=lambda *_a, **_kw: next(merchants),
        ):
            txns = parser._extract_transactions(
                cast(list[pdfplumber.page.Page], [page]), 2026
            )

        assert len(txns) == 1
        assert txns[0].merchant == "全聯福利中心"
        assert txns[0].amount == 75

    def test_filter_does_not_shift_subsequent_merchants(self):
        """After a filtered merchant, subsequent real merchants stay aligned."""
        parser = _make_parser()
        text = (
            "115/02/09 115/02/11 28 6713 TW\n"
            "115/02/12 115/02/23 75 6713 TW\n"
            "115/02/14 115/02/25 150 6713 TW\n"
        )
        page = make_mock_page(text)

        merchants = iter(["消費暨收費摘要表", "全聯福利中心", "統一超商"])
        with patch(
            "ccas.parser.banks.ctbc_v1._match_merchant_to_transaction",
            side_effect=lambda *_a, **_kw: next(merchants),
        ):
            txns = parser._extract_transactions(
                cast(list[pdfplumber.page.Page], [page]), 2026
            )

        assert len(txns) == 2
        assert txns[0].merchant == "全聯福利中心"
        assert txns[1].merchant == "統一超商"


class TestIsNonTransactionMerchant:
    """Tests for the _is_non_transaction_merchant helper."""

    @pytest.mark.parametrize(
        "merchant",
        ["消費暨收費摘要表", "帳單分期入帳", "帳單分期"],
    )
    def test_rejects_known_headers(self, merchant: str):
        assert _is_non_transaction_merchant(merchant) is True

    @pytest.mark.parametrize(
        "merchant",
        ["全聯福利中心", "統一超商", "本行扣繳", ""],
    )
    def test_accepts_real_merchants(self, merchant: str):
        assert _is_non_transaction_merchant(merchant) is False


# -- New tests for OCR normalization, zero-balance bills, and garbled PDFs --


class TestNormalizeOcrMerchant:
    """Tests for the _normalize_ocr_merchant helper."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Pi一金家便利商店", "全家便利商店"),
            ("Pi一全家便利商店", "全家便利商店"),
            ("Pi一了Y一ELEVEN", "7-ELEVEN"),
            ("Pi一了Y了一ELEVEN", "7-ELEVEN"),
            ("PIiI一了Y一ELEVEN", "7-ELEVEN"),
            ("連加未麥芝勞", "麥當勞"),
            ("台灣麥當馮餐廳一489", "麥當勞餐廳一489"),
            ("無印恨品", "無印良品"),
            ("全聯福利中心", "全聯福利中心"),  # no-op for clean input
            ("", ""),
        ],
    )
    def test_normalizes_known_ocr_errors(self, raw: str, expected: str):
        from ccas.parser.banks.ctbc_v1 import _normalize_ocr_merchant

        assert _normalize_ocr_merchant(raw) == expected


class TestIsGarbled:
    """Tests for the _is_garbled helper."""

    def test_detects_garbled_text(self):
        from ccas.parser.banks.ctbc_v1 import _is_garbled

        assert _is_garbled(CTBC_GARBLED_TEXT) is True

    def test_clean_text_not_garbled(self):
        from ccas.parser.banks.ctbc_v1 import _is_garbled

        assert _is_garbled(CTBC_ROC_FIRST_PAGE_TEXT) is False

    def test_empty_text_not_garbled(self):
        from ccas.parser.banks.ctbc_v1 import _is_garbled

        assert _is_garbled("") is False

    def test_few_cid_tokens_not_garbled(self):
        from ccas.parser.banks.ctbc_v1 import _is_garbled

        assert _is_garbled("(cid:1)(cid:2)(cid:3)") is False


class TestExtractTotalAmountPage1:
    """Tests for _extract_total_amount_page1."""

    def test_extracts_zero_amount(self):
        from ccas.parser.banks.ctbc_v1 import _extract_total_amount_page1

        assert _extract_total_amount_page1(CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT) == 0

    def test_extracts_nonzero_amount(self):
        from ccas.parser.banks.ctbc_v1 import _extract_total_amount_page1

        text = (
            "115 03 1 / 3\n402\n115/04 7.7\ni APP\n80,000\n"
            "/ 80,000/ 80,000\n( ) 2,967 7.7%\n115/04\n1,000 ( )\n"
        )
        assert _extract_total_amount_page1(text) == 2967

    def test_returns_none_when_no_rate_line(self):
        from ccas.parser.banks.ctbc_v1 import _extract_total_amount_page1

        assert _extract_total_amount_page1("no useful content here") is None

    def test_does_not_misidentify_credit_limit(self):
        from ccas.parser.banks.ctbc_v1 import _extract_total_amount_page1

        # "80,000" appears on page 1 but without a rate% suffix — must not match it
        result = _extract_total_amount_page1(CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT)
        assert result != 80000


class TestExtractDueDatePage1:
    """Tests for _extract_due_date_page1."""

    def test_extracts_year_month_defaults_to_day28(self):
        from ccas.parser.banks.ctbc_v1 import _extract_due_date_page1

        result = _extract_due_date_page1(CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT)
        assert result == date(2024, 1, 28)

    def test_returns_none_when_no_roc_year_month(self):
        from ccas.parser.banks.ctbc_v1 import _extract_due_date_page1

        assert _extract_due_date_page1("no dates here") is None

    def test_does_not_match_full_roc_date(self):
        from ccas.parser.banks.ctbc_v1 import _extract_due_date_page1

        # A page with only full NNN/MM/DD dates should not be matched by year+month regex
        text_with_full_dates = "113/01/15\n113/01/20\n"
        result = _extract_due_date_page1(text_with_full_dates)
        assert result is None


class TestExtractSummaryZeroBalanceFallback:
    """Integration test: 2-page zero-balance bill uses page1 fallbacks."""

    def test_two_page_zero_balance_parses_correctly(self):
        parser = _make_parser()
        page1 = make_mock_page(CTBC_ROC_ZERO_BALANCE_PAGE1_TEXT)
        page2 = make_mock_page(CTBC_ROC_ZERO_BALANCE_TXN_PAGE_TEXT)

        billing_month, total_amount, due_date = parser._extract_summary([page1, page2])

        assert billing_month == "2024-01"
        assert total_amount == 0
        assert due_date.day == 28
        assert due_date.month == 1
        assert due_date.year == 2024


class TestCanParseOcrFallback:
    """Tests for can_parse() OCR fallback on garbled PDFs."""

    def test_can_parse_uses_ocr_when_text_fails(self):
        """can_parse returns True when pdfplumber text fails but OCR identifies CTBC."""
        from unittest.mock import MagicMock, patch as _patch
        from pathlib import Path

        from ccas.parser.banks.ctbc_v1 import CtbcV1Parser

        parser = CtbcV1Parser()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = CTBC_GARBLED_TEXT
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with _patch("ccas.parser.banks.ctbc_v1.pdfplumber") as mock_plumber, _patch(
            "ccas.parser.banks.ctbc_v1.is_ocr_available", return_value=True
        ), _patch(
            "ccas.parser.banks.ctbc_v1._ocr_page_full",
            return_value=CTBC_ROC_FIRST_PAGE_TEXT,
        ):
            mock_plumber.open.return_value = mock_pdf
            assert parser.can_parse(Path("dummy.pdf")) is True

    def test_can_parse_returns_false_when_both_text_and_ocr_fail(self):
        """can_parse returns False when both pdfplumber and OCR yield unrecognized text."""
        from unittest.mock import MagicMock, patch as _patch
        from pathlib import Path

        from ccas.parser.banks.ctbc_v1 import CtbcV1Parser

        parser = CtbcV1Parser()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = CTBC_GARBLED_TEXT
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with _patch("ccas.parser.banks.ctbc_v1.pdfplumber") as mock_plumber, _patch(
            "ccas.parser.banks.ctbc_v1.is_ocr_available", return_value=True
        ), _patch("ccas.parser.banks.ctbc_v1._ocr_page_full", return_value=""):
            mock_plumber.open.return_value = mock_pdf
            assert parser.can_parse(Path("dummy.pdf")) is False
