"""run_parse_job 進度回報失敗防護的單元測試。

進度回報屬於純 UI；reporter 在 item loop 的 finally 內 raise 時，
不可中斷批次或讓已 flush 未 commit 的資料被 rollback。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.parser.job import run_parse_job


class RaisingReporter:
    """stage_item_done 一律 raise 的 ProgressReporter 假件。"""

    def __init__(self) -> None:
        self.item_calls = 0

    async def stage_started(self, stage: str, total: int) -> None:
        pass

    async def stage_item_done(self, stage: str, processed: int) -> None:
        self.item_calls += 1
        raise RuntimeError("reporter boom")

    async def stage_finished(
        self,
        stage: str,
        ok: int,
        fail: int,
        elapsed_ms: int,
        *,
        counts: Mapping[str, int] | None = None,
        errors: Sequence[str] | None = None,
    ) -> None:
        pass


async def test_reporter_failure_does_not_abort_parse_batch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reporter = RaisingReporter()
    session = AsyncMock()

    attachments = [MagicMock(id=i) for i in range(3)]
    process_mock = AsyncMock(return_value=None)

    with (
        patch(
            "ccas.parser.job.fetch_parseable_attachments",
            new=AsyncMock(return_value=attachments),
        ),
        patch("ccas.parser.job._process_attachment", new=process_mock),
        caplog.at_level(logging.WARNING, logger="ccas.parser.job"),
    ):
        await run_parse_job(session, options=None, reporter=reporter)

    # Every item was still processed despite the reporter raising each time.
    assert process_mock.await_count == 3
    assert reporter.item_calls == 3
    # Batch reached commit (no rollback caused by progress reporting).
    session.commit.assert_awaited_once()
    # Swallow-with-log: failure is logged, not silent.
    assert "parse progress reporting failed" in caplog.text
