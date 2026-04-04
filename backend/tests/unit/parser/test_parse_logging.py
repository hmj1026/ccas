"""Parse failure structured logging tests.

Verifies that _try_parse() produces structured log output with
pdf_filename, bank_code, error_type, and error_detail fields.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock

from ccas.parser.base import BankParser, ParseError
from ccas.parser.job import _try_parse
from ccas.parser.result import ParseResult


class _FakeParser(BankParser):
    def __init__(
        self,
        bank_code: str = "TEST",
        version: str = "v1",
        can_parse_result: bool = True,
        parse_error: Exception | None = None,
    ):
        self.bank_code = bank_code
        self.version = version
        self._can_parse_result = can_parse_result
        self._parse_error = parse_error

    def can_parse(self, pdf_path: Path) -> bool:
        return self._can_parse_result

    def parse(self, pdf_path: Path) -> ParseResult:
        if self._parse_error:
            raise self._parse_error
        return MagicMock(spec=ParseResult)  # type: ignore[return-value]


class TestTryParseLogging:
    def test_successful_match_logs_info(self, caplog):
        parser = _FakeParser()
        with caplog.at_level(logging.INFO, logger="ccas.parser.job"):
            success, result, error = _try_parse([parser], Path("/tmp/test.pdf"))

        assert success is True
        assert any("parser 匹配成功" in r.message for r in caplog.records)

    def test_parse_error_logs_structured_fields(self, caplog):
        parser = _FakeParser(
            parse_error=ParseError("帳單摘要缺失", reason="找不到帳單月份"),
        )
        with caplog.at_level(logging.ERROR, logger="ccas.parser.job"):
            success, _, _ = _try_parse([parser], Path("/tmp/bill.pdf"))

        assert success is False
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        record = error_records[0]
        assert record.pdf_filename == "bill.pdf"  # type: ignore[attr-defined]
        assert record.bank_code == "TEST"  # type: ignore[attr-defined]
        assert record.error_type == "ParseError"  # type: ignore[attr-defined]

    def test_unexpected_error_logs_with_traceback(self, caplog):
        parser = _FakeParser(parse_error=RuntimeError("crash"))
        with caplog.at_level(logging.ERROR, logger="ccas.parser.job"):
            success, _, _ = _try_parse([parser], Path("/tmp/crash.pdf"))

        assert success is False
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        record = error_records[0]
        assert record.error_type == "RuntimeError"  # type: ignore[attr-defined]
        assert record.exc_info is not None

    def test_all_parsers_fail_logs_warning(self, caplog):
        parsers = [
            _FakeParser(bank_code="A", can_parse_result=False),
            _FakeParser(bank_code="B", can_parse_result=False),
        ]
        with caplog.at_level(logging.WARNING, logger="ccas.parser.job"):
            success, _, _ = _try_parse(parsers, Path("/tmp/unknown.pdf"))

        assert success is False
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) >= 1
        record = warn_records[0]
        assert record.pdf_filename == "unknown.pdf"  # type: ignore[attr-defined]
        assert "A/v1" in str(record.attempted_parsers)  # type: ignore[attr-defined]

    def test_can_parse_false_logs_debug(self, caplog):
        parser = _FakeParser(can_parse_result=False)
        with caplog.at_level(logging.DEBUG, logger="ccas.parser.job"):
            _try_parse([parser], Path("/tmp/skip.pdf"))

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("can_parse=False" in r.message for r in debug_records)
