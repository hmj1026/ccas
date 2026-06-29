"""Unit tests for ccas.parser.job coordination logic.

Focuses on _process_attachment branch handling (missing path, path escape,
no parser, zero-balance skip, all-parsers-fail, dedupe skip, force re-parse,
fresh create) and run_parse_job batch orchestration (empty batch, default
reporter, per-item rollback on unexpected failure).

The CPU-bound _try_parse runs via asyncio.to_thread; tests patch it with a
plain sync callable. The patched Settings always carries a REAL numeric
pdf_parse_timeout_seconds so asyncio.wait_for does not raise.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ccas.parser.job import ParseSummary, _process_attachment, run_parse_job
from ccas.parser.registry import ParserNotFoundError
from ccas.storage.models import StagedAttachmentStatus


def _make_settings() -> MagicMock:
    # pdf_parse_timeout_seconds MUST be a real number: asyncio.wait_for uses it.
    return MagicMock(staging_dir="./data/staging", pdf_parse_timeout_seconds=30.0)


def _make_attachment(
    *,
    staged_path: str | None = "CTBC/bill.pdf",
    bank_code: str = "CTBC",
    original_filename: str = "bill.pdf",
) -> MagicMock:
    return MagicMock(
        bank_code=bank_code,
        staged_path=staged_path,
        original_filename=original_filename,
    )


def _enter_core_patches(
    stack: ExitStack,
    try_parse,
    *,
    bill_exists: bool = False,
) -> dict[str, AsyncMock]:
    """Patch the per-attachment collaborators and return the AsyncMocks."""
    update_mock = AsyncMock()
    check_mock = AsyncMock(return_value=bill_exists)
    create_mock = AsyncMock()
    delete_mock = AsyncMock()
    stack.enter_context(
        patch("ccas.parser.job.get_settings", return_value=_make_settings())
    )
    stack.enter_context(
        patch(
            "ccas.parser.job.resolve_staged_path",
            return_value=Path("/tmp/CTBC/bill.pdf"),
        )
    )
    stack.enter_context(
        patch("ccas.parser.job.registry.resolve", return_value=[MagicMock()])
    )
    stack.enter_context(patch("ccas.parser.job._try_parse", new=try_parse))
    stack.enter_context(
        patch("ccas.parser.job.update_attachment_status", new=update_mock)
    )
    stack.enter_context(patch("ccas.parser.job.check_bill_exists", new=check_mock))
    stack.enter_context(
        patch("ccas.parser.job.create_bill_and_transactions", new=create_mock)
    )
    stack.enter_context(patch("ccas.parser.job.delete_existing_bill", new=delete_mock))
    return {
        "update": update_mock,
        "check": check_mock,
        "create": create_mock,
        "delete": delete_mock,
    }


# -- _process_attachment: early-exit failure branches --


class TestProcessAttachmentFailures:
    async def test_missing_staged_path_marks_failed(self):
        attachment = _make_attachment(staged_path=None)
        summary = ParseSummary()
        update_mock = AsyncMock()

        with patch("ccas.parser.job.update_attachment_status", new=update_mock):
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.failed_count == 1
        assert any("缺少 staged_path" in e for e in summary.errors)
        assert (
            update_mock.await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_FAILED
        )

    async def test_path_escape_marks_failed(self):
        attachment = _make_attachment()
        summary = ParseSummary()
        update_mock = AsyncMock()

        with (
            patch("ccas.parser.job.get_settings", return_value=_make_settings()),
            patch(
                "ccas.parser.job.resolve_staged_path",
                side_effect=ValueError("escape"),
            ),
            patch("ccas.parser.job.update_attachment_status", new=update_mock),
        ):
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.failed_count == 1
        assert any("逃逸" in e for e in summary.errors)
        assert (
            update_mock.await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_FAILED
        )

    async def test_no_parser_found_marks_failed(self):
        attachment = _make_attachment()
        summary = ParseSummary()
        update_mock = AsyncMock()

        with (
            patch("ccas.parser.job.get_settings", return_value=_make_settings()),
            patch(
                "ccas.parser.job.resolve_staged_path",
                return_value=Path("/tmp/CTBC/bill.pdf"),
            ),
            patch(
                "ccas.parser.job.registry.resolve",
                side_effect=ParserNotFoundError("no parser"),
            ),
            patch("ccas.parser.job.update_attachment_status", new=update_mock),
        ):
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.failed_count == 1
        assert any("找不到 parser" in e for e in summary.errors)
        assert (
            update_mock.await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_FAILED
        )

    async def test_parse_timeout_marks_failed(self):
        """A poison-PDF timeout marks PARSE_FAILED without aborting the worker."""
        attachment = _make_attachment(original_filename="poison.pdf")
        summary = ParseSummary()
        update_mock = AsyncMock()

        with (
            patch("ccas.parser.job.get_settings", return_value=_make_settings()),
            patch(
                "ccas.parser.job.resolve_staged_path",
                return_value=Path("/tmp/CTBC/bill.pdf"),
            ),
            patch("ccas.parser.job.registry.resolve", return_value=[MagicMock()]),
            # to_thread returns a non-coroutine so wait_for can be replaced cleanly.
            patch("ccas.parser.job.asyncio.to_thread", new=MagicMock()),
            patch(
                "ccas.parser.job.asyncio.wait_for",
                new=AsyncMock(side_effect=TimeoutError),
            ),
            patch("ccas.parser.job.update_attachment_status", new=update_mock),
        ):
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.failed_count == 1
        assert any("逾時" in e for e in summary.errors)
        assert (
            update_mock.await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_FAILED
        )

    async def test_uses_bank_config_active_version(self):
        """bank_config is forwarded to registry.resolve as active_parser_version."""
        attachment = _make_attachment()
        summary = ParseSummary()
        bank_config = MagicMock(active_parser_version="v2")
        resolve_mock = MagicMock(return_value=[MagicMock()])

        def _try_parse(_c, _p):
            return True, MagicMock(bank_code="CTBC", billing_month="2026-03"), ""

        with ExitStack() as stack:
            stack.enter_context(
                patch("ccas.parser.job.get_settings", return_value=_make_settings())
            )
            stack.enter_context(
                patch(
                    "ccas.parser.job.resolve_staged_path",
                    return_value=Path("/tmp/CTBC/bill.pdf"),
                )
            )
            stack.enter_context(
                patch("ccas.parser.job.registry.resolve", new=resolve_mock)
            )
            stack.enter_context(patch("ccas.parser.job._try_parse", new=_try_parse))
            stack.enter_context(
                patch("ccas.parser.job.update_attachment_status", new=AsyncMock())
            )
            stack.enter_context(
                patch(
                    "ccas.parser.job.check_bill_exists",
                    new=AsyncMock(return_value=False),
                )
            )
            stack.enter_context(
                patch("ccas.parser.job.create_bill_and_transactions", new=AsyncMock())
            )
            await _process_attachment(attachment, AsyncMock(), summary, bank_config)

        assert resolve_mock.call_args.args == ("CTBC", "v2")


# -- _process_attachment: parse-result branches (240-319) --


class TestProcessAttachmentParseOutcomes:
    async def test_zero_balance_is_skipped_not_failed(self):
        attachment = _make_attachment()
        summary = ParseSummary()

        def _try_parse(_c, _p):
            return False, None, "zero-balance historical bill"

        with ExitStack() as stack:
            mocks = _enter_core_patches(stack, _try_parse)
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.skipped_count == 1
        assert summary.failed_count == 0
        assert (
            mocks["update"].await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_SKIPPED
        )

    async def test_all_parsers_fail_marks_failed(self):
        attachment = _make_attachment()
        summary = ParseSummary()

        def _try_parse(_c, _p):
            return False, None, "CTBC/v1: can_parse=False"

        with ExitStack() as stack:
            mocks = _enter_core_patches(stack, _try_parse)
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.failed_count == 1
        assert any("所有 parser 皆失敗" in e for e in summary.errors)
        assert (
            mocks["update"].await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSE_FAILED
        )

    async def test_existing_bill_without_force_is_skipped(self):
        attachment = _make_attachment()
        summary = ParseSummary()
        parse_result = MagicMock(bank_code="CTBC", billing_month="2026-03")

        def _try_parse(_c, _p):
            return True, parse_result, ""

        with ExitStack() as stack:
            mocks = _enter_core_patches(stack, _try_parse, bill_exists=True)
            await _process_attachment(
                attachment, AsyncMock(), summary, None, force=False
            )

        assert summary.skipped_count == 1
        assert summary.parsed_count == 0
        mocks["create"].assert_not_awaited()
        mocks["delete"].assert_not_awaited()
        assert (
            mocks["update"].await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSED
        )

    async def test_existing_bill_with_force_deletes_and_recreates(self):
        attachment = _make_attachment()
        summary = ParseSummary()
        parse_result = MagicMock(bank_code="CTBC", billing_month="2026-03")

        def _try_parse(_c, _p):
            return True, parse_result, ""

        with ExitStack() as stack:
            mocks = _enter_core_patches(stack, _try_parse, bill_exists=True)
            await _process_attachment(
                attachment, AsyncMock(), summary, None, force=True
            )

        assert summary.parsed_count == 1
        mocks["delete"].assert_awaited_once()
        mocks["create"].assert_awaited_once()
        assert (
            mocks["update"].await_args_list[-1].kwargs["status"]
            == StagedAttachmentStatus.PARSED
        )

    async def test_new_bill_is_created(self):
        attachment = _make_attachment()
        summary = ParseSummary()
        parse_result = MagicMock(bank_code="CTBC", billing_month="2026-03")

        def _try_parse(_c, _p):
            return True, parse_result, ""

        with ExitStack() as stack:
            mocks = _enter_core_patches(stack, _try_parse, bill_exists=False)
            await _process_attachment(attachment, AsyncMock(), summary, None)

        assert summary.parsed_count == 1
        mocks["delete"].assert_not_awaited()
        mocks["create"].assert_awaited_once()
        # file_path forwarded as the resolved staged path string.
        assert (
            mocks["create"].await_args_list[-1].kwargs["file_path"]
            == "/tmp/CTBC/bill.pdf"
        )


# -- run_parse_job: batch orchestration --


class TestRunParseJob:
    async def test_empty_batch_returns_early(self):
        session = AsyncMock()

        with patch(
            "ccas.parser.job.fetch_parseable_attachments",
            new=AsyncMock(return_value=[]),
        ):
            summary = await run_parse_job(session)

        assert summary == ParseSummary()
        session.commit.assert_not_awaited()

    async def test_default_reporter_does_not_crash_on_empty(self):
        """reporter=None must be wrapped in NoopProgressReporter (line 348)."""
        session = AsyncMock()

        with patch(
            "ccas.parser.job.fetch_parseable_attachments",
            new=AsyncMock(return_value=[]),
        ):
            summary = await run_parse_job(session, options=None, reporter=None)

        assert summary.parsed_count == 0

    async def test_successful_batch_commits_per_item_and_reports(self):
        session = AsyncMock()
        reporter = AsyncMock()
        attachments = [
            _make_attachment(bank_code="CTBC", original_filename="a.pdf"),
            _make_attachment(bank_code="ESUN", original_filename="b.pdf"),
        ]

        with (
            patch(
                "ccas.parser.job.fetch_parseable_attachments",
                new=AsyncMock(return_value=attachments),
            ),
            patch("ccas.parser.job.get_bank_config", new=AsyncMock(return_value=None)),
            patch(
                "ccas.parser.job._process_attachment", new=AsyncMock(return_value=None)
            ),
        ):
            await run_parse_job(session, reporter=reporter)

        # Each item commits independently and reports progress; no rollback.
        assert session.commit.await_count == 2
        session.rollback.assert_not_awaited()
        reporter.stage_started.assert_awaited_once_with("parse", total=2)
        assert reporter.stage_item_done.await_count == 2

    async def test_item_exception_rolls_back_and_continues(self, caplog):
        session = AsyncMock()
        attachments = [
            _make_attachment(bank_code="CTBC", original_filename="a.pdf"),
            _make_attachment(bank_code="CTBC", original_filename="b.pdf"),
        ]

        with (
            patch(
                "ccas.parser.job.fetch_parseable_attachments",
                new=AsyncMock(return_value=attachments),
            ),
            patch("ccas.parser.job.get_bank_config", new=AsyncMock(return_value=None)),
            patch(
                "ccas.parser.job._process_attachment",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            caplog.at_level(logging.ERROR, logger="ccas.parser.job"),
        ):
            await run_parse_job(session)

        # Both items attempted; each failure rolled back, no commit happened.
        assert session.rollback.await_count == 2
        session.commit.assert_not_awaited()
        assert "parse item failed unexpectedly" in caplog.text
