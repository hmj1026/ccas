"""Seam tests for ``ccas.parser.intake.ParserIntake`` using fake ports.

Covers process_one branch handling (missing path, path escape, no parser,
timeout, zero-balance skip, all-fail, dedupe skip, force re-parse, fresh
create, active-version-first ordering) and run() batch orchestration (empty
batch, item-exception rollback+continue, reporter-guard swallow, and the
"persistence failure on 2nd item preserves 1st item" semantics) — all against
in-memory fakes, no real DB.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ccas.parser.base import BankParser, ParseError
from ccas.parser.intake import ParserIntake, ParseSummary
from ccas.parser.registry import _ParserRegistry
from ccas.parser.result import ParseResult, TransactionItem
from ccas.storage.models import StagedAttachmentStatus
from ccas.storage.paths import resolve_staged_path

TEST_STAGING_DIR = "/tmp/test-staging-intake"


class FakeParser(BankParser):
    """成功解析的假 parser。"""

    def __init__(
        self, bank_code: str, version: str, result: ParseResult | None = None
    ) -> None:
        self.bank_code = bank_code
        self.version = version
        self._result = result

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        assert self._result is not None
        return self._result


class FakeCannotParseParser(BankParser):
    """can_parse=False 的假 parser。"""

    def __init__(self, bank_code: str, version: str) -> None:
        self.bank_code = bank_code
        self.version = version

    def can_parse(self, pdf_path: Path) -> bool:
        return False

    def parse(self, pdf_path: Path) -> ParseResult:
        raise ParseError("不應被呼叫")


class FakeZeroBalanceParser(BankParser):
    """parse() 拋出 zero-balance ParseError 的假 parser。"""

    def __init__(self, bank_code: str, version: str) -> None:
        self.bank_code = bank_code
        self.version = version

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        raise ParseError("zero-balance historical bill")


class SlowParser(BankParser):
    """parse() 阻塞至 release event 被設定的假 parser（模擬毒藥 PDF）。"""

    def __init__(self, bank_code: str, version: str, release: threading.Event) -> None:
        self.bank_code = bank_code
        self.version = version
        self._release = release

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        self._release.wait(timeout=5.0)
        return _make_parse_result()


def _make_parse_result(
    bank_code: str = "CTBC", billing_month: str = "2026-03"
) -> ParseResult:
    return ParseResult(
        bank_code=bank_code,
        billing_month=billing_month,
        total_amount=5000,
        due_date=date(2026, 4, 15),
        transactions=(
            TransactionItem(trans_date=date(2026, 3, 1), merchant="星巴克", amount=150),
        ),
    )


def _make_attachment(
    *,
    bank_code: str = "CTBC",
    staged_path: str | None = "CTBC/bill.pdf",
    original_filename: str = "bill.pdf",
) -> MagicMock:
    return MagicMock(
        bank_code=bank_code,
        staged_path=staged_path,
        original_filename=original_filename,
    )


class InMemoryBankConfigPort:
    """記憶體內的 BankConfigPort 假件。"""

    def __init__(self, versions: dict[str, str | None] | None = None) -> None:
        self.versions = versions or {}

    async def get_active_version(self, session: Any, bank_code: str) -> str | None:
        return self.versions.get(bank_code)


class InMemoryParsePersistencePort:
    """記憶體內的 ParsePersistencePort 假件，記錄呼叫供測試斷言。"""

    def __init__(self, attachments: list | None = None) -> None:
        self.attachments = list(attachments or [])
        self.existing_bills: set[tuple[str, str]] = set()
        self.created: list[tuple[ParseResult, str | None]] = []
        self.deleted: list[tuple[str, str]] = []
        self.status_calls: list[tuple[Any, StagedAttachmentStatus, str | None]] = []
        self.fail_create = False

    async def fetch_parseable(self, session: Any, options: Any = None) -> list:
        return self.attachments

    async def bill_exists(
        self, session: Any, bank_code: str, billing_month: str
    ) -> bool:
        return (bank_code, billing_month) in self.existing_bills

    async def delete_bill(
        self, session: Any, bank_code: str, billing_month: str
    ) -> bool:
        existed = (bank_code, billing_month) in self.existing_bills
        self.existing_bills.discard((bank_code, billing_month))
        self.deleted.append((bank_code, billing_month))
        return existed

    async def create_bill(
        self, session: Any, result: ParseResult, *, file_path: str | None
    ) -> Any:
        if self.fail_create:
            raise RuntimeError("create_bill boom")
        self.created.append((result, file_path))
        self.existing_bills.add((result.bank_code, result.billing_month))
        return MagicMock()

    async def set_status(
        self,
        session: Any,
        attachment: Any,
        *,
        status: StagedAttachmentStatus,
        error_reason: str | None = None,
    ) -> None:
        self.status_calls.append((attachment, status, error_reason))


def _make_intake(
    registry: _ParserRegistry | None = None,
    config: InMemoryBankConfigPort | None = None,
    persistence: InMemoryParsePersistencePort | None = None,
    timeout: float = 30.0,
) -> tuple[ParserIntake, InMemoryBankConfigPort, InMemoryParsePersistencePort]:
    reg = registry if registry is not None else _ParserRegistry()
    cfg = config if config is not None else InMemoryBankConfigPort()
    persist = persistence if persistence is not None else InMemoryParsePersistencePort()
    intake = ParserIntake(
        registry=reg,
        config=cfg,
        persistence=persist,
        timeout_provider=lambda: timeout,
        staging_root_provider=lambda: TEST_STAGING_DIR,
    )
    return intake, cfg, persist


# -- process_one: early-exit failure branches --


class TestProcessOneFailures:
    async def test_missing_staged_path_marks_failed(self) -> None:
        intake, _cfg, persist = _make_intake()
        attachment = _make_attachment(staged_path=None)
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.failed_count == 1
        assert any("缺少 staged_path" in e for e in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED

    async def test_path_escape_marks_failed(self) -> None:
        intake, _cfg, persist = _make_intake()
        attachment = _make_attachment(staged_path="../../etc/passwd")
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.failed_count == 1
        assert any("逃逸" in e for e in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED

    async def test_no_parser_registered_marks_failed(self) -> None:
        intake, _cfg, persist = _make_intake()
        attachment = _make_attachment(
            bank_code="UNKNOWN", staged_path="UNKNOWN/bill.pdf"
        )
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.failed_count == 1
        assert any("找不到 parser" in e for e in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED

    async def test_parse_timeout_marks_failed(self) -> None:
        registry = _ParserRegistry()
        release = threading.Event()
        registry.register(SlowParser("CTBC", "v1", release))
        intake, _cfg, persist = _make_intake(registry=registry, timeout=0.05)
        attachment = _make_attachment()
        summary = ParseSummary()

        try:
            await intake.process_one(AsyncMock(), attachment, summary, None)
        finally:
            release.set()  # let the leaked background thread finish

        assert summary.failed_count == 1
        assert any("逾時" in e for e in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED

    async def test_active_version_forwarded_to_registry_resolve(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        registry.register(FakeParser("CTBC", "v2", _make_parse_result()))
        intake, _cfg, persist = _make_intake(registry=registry)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, "v2")

        assert summary.parsed_count == 1
        assert persist.created[-1][0].bank_code == "CTBC"


# -- process_one: parse-result branches --


class TestProcessOneParseOutcomes:
    async def test_zero_balance_is_skipped_not_failed(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeZeroBalanceParser("CTBC", "v1"))
        intake, _cfg, persist = _make_intake(registry=registry)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.skipped_count == 1
        assert summary.failed_count == 0
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_SKIPPED

    async def test_all_parsers_fail_marks_failed(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeCannotParseParser("CTBC", "v1"))
        intake, _cfg, persist = _make_intake(registry=registry)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.failed_count == 1
        assert any("所有 parser 皆失敗" in e for e in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED

    async def test_existing_bill_without_force_is_skipped(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        persistence = InMemoryParsePersistencePort()
        persistence.existing_bills.add(("CTBC", "2026-03"))
        intake, _cfg, persist = _make_intake(registry=registry, persistence=persistence)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None, force=False)

        assert summary.skipped_count == 1
        assert summary.parsed_count == 0
        assert persist.created == []
        assert persist.deleted == []
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSED

    async def test_existing_bill_with_force_deletes_and_recreates(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        persistence = InMemoryParsePersistencePort()
        persistence.existing_bills.add(("CTBC", "2026-03"))
        intake, _cfg, persist = _make_intake(registry=registry, persistence=persistence)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None, force=True)

        assert summary.parsed_count == 1
        assert persist.deleted == [("CTBC", "2026-03")]
        assert len(persist.created) == 1
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSED

    async def test_new_bill_is_created_with_file_path(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        intake, _cfg, persist = _make_intake(registry=registry)
        attachment = _make_attachment()
        summary = ParseSummary()

        await intake.process_one(AsyncMock(), attachment, summary, None)

        assert summary.parsed_count == 1
        assert persist.deleted == []
        assert len(persist.created) == 1
        _, file_path = persist.created[-1]
        assert file_path == str(resolve_staged_path(TEST_STAGING_DIR, "CTBC/bill.pdf"))


# -- registry ordering (active-version-first + fallback) --


class TestRegistryOrdering:
    async def test_active_version_first_then_fallback_order(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1"))
        registry.register(FakeParser("CTBC", "v2"))
        registry.register(FakeParser("CTBC", "v3"))

        candidates = registry.resolve("CTBC", active_version="v2")
        assert [p.version for p in candidates] == ["v2", "v3", "v1"]


# -- run(): batch orchestration --


class TestRun:
    async def test_empty_batch_returns_early(self) -> None:
        intake, _cfg, _persist = _make_intake()
        session = AsyncMock()

        summary = await intake.run(session)

        assert summary == ParseSummary()
        session.commit.assert_not_awaited()

    async def test_item_exception_rolls_back_and_continues(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry = _ParserRegistry()
        persistence = InMemoryParsePersistencePort(
            attachments=[
                _make_attachment(bank_code="CTBC", original_filename="a.pdf"),
                _make_attachment(bank_code="CTBC", original_filename="b.pdf"),
            ]
        )
        intake, _cfg, _persist = _make_intake(
            registry=registry, persistence=persistence
        )
        intake.process_one = AsyncMock(side_effect=RuntimeError("boom"))
        session = AsyncMock()

        with caplog.at_level(logging.ERROR, logger="ccas.parser.intake"):
            summary = await intake.run(session)

        assert session.rollback.await_count == 2
        assert session.commit.await_count == 2
        assert summary.failed_count == 2
        assert len(summary.errors) == 2
        assert "parse item failed unexpectedly" in caplog.text

    async def test_reporter_guard_swallows_reporter_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        persistence = InMemoryParsePersistencePort(
            attachments=[_make_attachment(bank_code="CTBC")]
        )
        intake, _cfg, _persist = _make_intake(
            registry=registry, persistence=persistence
        )
        session = AsyncMock()

        class RaisingReporter:
            async def stage_started(self, stage: str, total: int) -> None:
                pass

            async def stage_item_done(self, stage: str, processed: int) -> None:
                raise RuntimeError("reporter boom")

            async def stage_finished(self, *args: object, **kwargs: object) -> None:
                pass

        with caplog.at_level(logging.WARNING, logger="ccas.parser.intake"):
            summary = await intake.run(session, reporter=RaisingReporter())

        assert summary.parsed_count == 1
        assert session.commit.await_count == 1
        session.rollback.assert_not_awaited()
        assert "parse progress reporting failed" in caplog.text

    async def test_persistence_failure_on_second_item_preserves_first(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A 2nd-item persistence failure is visible without undoing item 1."""

        class DistinctBillingMonthParser(BankParser):
            """billing_month 依 pdf 檔名而異，避免第二筆命中去重複略過。"""

            bank_code = "CTBC"
            version = "v1"

            def can_parse(self, pdf_path: Path) -> bool:
                return True

            def parse(self, pdf_path: Path) -> ParseResult:
                month = "03" if pdf_path.name == "a.pdf" else "04"
                return _make_parse_result(billing_month=f"2026-{month}")

        registry = _ParserRegistry()
        registry.register(DistinctBillingMonthParser())
        persistence = InMemoryParsePersistencePort(
            attachments=[
                _make_attachment(
                    bank_code="CTBC",
                    staged_path="CTBC/a.pdf",
                    original_filename="a.pdf",
                ),
                _make_attachment(
                    bank_code="CTBC",
                    staged_path="CTBC/b.pdf",
                    original_filename="b.pdf",
                ),
            ]
        )
        intake, _cfg, persist = _make_intake(registry=registry, persistence=persistence)
        session = AsyncMock()

        call_count = 0
        original_create_bill = persist.create_bill

        async def flaky_create_bill(session, result, *, file_path):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("persistence boom")
            return await original_create_bill(session, result, file_path=file_path)

        persist.create_bill = flaky_create_bill

        with caplog.at_level(logging.ERROR, logger="ccas.parser.intake"):
            summary = await intake.run(session)

        # 1st item preserved: parsed_count bumped once, one bill created.
        assert summary.parsed_count == 1
        assert len(persist.created) == 1
        assert summary.failed_count == 1
        assert any("persistence boom" in error for error in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED
        # First item + durable failure status for the second item.
        assert session.commit.await_count == 2
        assert session.rollback.await_count == 1
        assert "parse item failed unexpectedly" in caplog.text

    async def test_commit_failure_reclassifies_item_from_parsed_to_failed(self) -> None:
        registry = _ParserRegistry()
        registry.register(FakeParser("CTBC", "v1", _make_parse_result()))
        attachment = _make_attachment(bank_code="CTBC")
        persistence = InMemoryParsePersistencePort(attachments=[attachment])
        intake, _cfg, persist = _make_intake(registry=registry, persistence=persistence)
        session = AsyncMock()
        session.commit.side_effect = [RuntimeError("commit boom"), None]

        summary = await intake.run(session)

        assert summary.parsed_count == 0
        assert summary.failed_count == 1
        assert any("commit boom" in error for error in summary.errors)
        assert persist.status_calls[-1][1] == StagedAttachmentStatus.PARSE_FAILED
