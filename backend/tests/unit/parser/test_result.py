"""ParseResult 與 parser contract 的單元測試。"""

from datetime import date
from pathlib import Path

import pytest

from ccas.parser.base import BankParser, ParseError
from ccas.parser.result import ParseResult, TransactionItem


class TestTransactionItem:
    """TransactionItem 資料結構測試。"""

    def test_required_fields(self) -> None:
        """必要欄位：trans_date, merchant, amount。"""
        item = TransactionItem(
            trans_date=date(2026, 3, 15),
            merchant="全聯",
            amount=350,
        )
        assert item.trans_date == date(2026, 3, 15)
        assert item.merchant == "全聯"
        assert item.amount == 350

    def test_optional_fields_default(self) -> None:
        """可選欄位預設值。"""
        item = TransactionItem(
            trans_date=date(2026, 3, 15),
            merchant="全聯",
            amount=350,
        )
        assert item.posting_date is None
        assert item.currency == "TWD"
        assert item.original_amount is None
        assert item.card_last4 is None
        assert item.installment_current is None
        assert item.installment_total is None

    def test_frozen_immutability(self) -> None:
        """TransactionItem 為不可變。"""
        item = TransactionItem(
            trans_date=date(2026, 3, 15),
            merchant="全聯",
            amount=350,
        )
        with pytest.raises(AttributeError):
            item.amount = 999  # type: ignore[misc]

    def test_with_all_fields(self) -> None:
        """所有欄位皆可指定。"""
        item = TransactionItem(
            trans_date=date(2026, 3, 15),
            posting_date=date(2026, 3, 17),
            merchant="Amazon",
            amount=1500,
            currency="USD",
            original_amount=50,
            card_last4="1234",
            installment_current=1,
            installment_total=3,
        )
        assert item.posting_date == date(2026, 3, 17)
        assert item.currency == "USD"
        assert item.original_amount == 50
        assert item.card_last4 == "1234"
        assert item.installment_current == 1
        assert item.installment_total == 3


class TestParseResult:
    """ParseResult 資料結構測試。"""

    def test_parse_result_fields(self) -> None:
        """ParseResult 包含帳單摘要與交易明細。"""
        txns = (
            TransactionItem(trans_date=date(2026, 3, 1), merchant="星巴克", amount=150),
            TransactionItem(trans_date=date(2026, 3, 5), merchant="7-11", amount=85),
        )
        result = ParseResult(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=235,
            due_date=date(2026, 4, 15),
            transactions=txns,
        )
        assert result.bank_code == "CTBC"
        assert result.billing_month == "2026-03"
        assert result.total_amount == 235
        assert result.due_date == date(2026, 4, 15)
        assert len(result.transactions) == 2

    def test_frozen_immutability(self) -> None:
        """ParseResult 為不可變。"""
        result = ParseResult(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=100,
            due_date=date(2026, 4, 15),
            transactions=(),
        )
        with pytest.raises(AttributeError):
            result.total_amount = 999  # type: ignore[misc]

    def test_empty_transactions_allowed(self) -> None:
        """空交易列表是合法的（例如只有帳單摘要）。"""
        result = ParseResult(
            bank_code="CATHAY",
            billing_month="2026-02",
            total_amount=0,
            due_date=date(2026, 3, 20),
            transactions=(),
        )
        assert len(result.transactions) == 0


class TestBankParserContract:
    """驗證 BankParser 介面的 contract。"""

    def test_cannot_instantiate_abstract(self) -> None:
        """BankParser 不可直接實例化。"""
        with pytest.raises(TypeError):
            BankParser()  # type: ignore[abstract]

    def test_concrete_parser_must_implement_methods(self) -> None:
        """具體 parser 必須實作 can_parse 與 parse。"""

        class IncompleteParser(BankParser):
            bank_code = "TEST"
            version = "v1"

        with pytest.raises(TypeError):
            IncompleteParser()  # type: ignore[abstract]

    def test_concrete_parser_works(self) -> None:
        """完整實作的 parser 可正常運作。"""

        class ConcreteParser(BankParser):
            bank_code = "TEST"
            version = "v1"

            def can_parse(self, pdf_path: Path) -> bool:
                return True

            def parse(self, pdf_path: Path) -> ParseResult:
                return ParseResult(
                    bank_code="TEST",
                    billing_month="2026-01",
                    total_amount=100,
                    due_date=date(2026, 2, 15),
                    transactions=(),
                )

        parser = ConcreteParser()
        assert parser.can_parse(Path("/tmp/test.pdf"))
        result = parser.parse(Path("/tmp/test.pdf"))
        assert result.bank_code == "TEST"

    def test_parse_error_exception(self) -> None:
        """ParseError 可正確拋出。"""
        with pytest.raises(ParseError, match="test error"):
            raise ParseError("test error")
