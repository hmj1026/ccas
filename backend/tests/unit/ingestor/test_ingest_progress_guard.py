"""run_ingestion_job 進度回報失敗防護的單元測試。

進度回報屬於純 UI；reporter 在 item loop 的 finally 內 raise 時，
不可中斷批次或讓已 flush 未 commit 的資料被 rollback。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.job import run_ingestion_job


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


async def test_reporter_failure_does_not_abort_ingest_batch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reporter = RaisingReporter()
    session = AsyncMock()

    bank = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
    # One message with two PDF attachments, one web-fetch (html) message.
    msg_pdf = MagicMock(pdf_attachments=[MagicMock(), MagicMock()], html_body=None)
    msg_html = MagicMock(pdf_attachments=[], html_body="<html>fallback</html>")

    process_attachment_mock = AsyncMock(return_value=None)
    process_web_fetch_mock = AsyncMock(return_value=None)

    with (
        patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
        patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
        patch(
            "ccas.ingestor.job._fetch_active_banks",
            new=AsyncMock(return_value=[bank]),
        ),
        patch("ccas.ingestor.job.search_messages", return_value=[msg_pdf, msg_html]),
        patch("ccas.ingestor.job._process_attachment", new=process_attachment_mock),
        patch("ccas.ingestor.job._process_web_fetch", new=process_web_fetch_mock),
        caplog.at_level(logging.WARNING, logger="ccas.ingestor.job"),
    ):
        summary = await run_ingestion_job(session, options=None, reporter=reporter)

    # Every item was still processed despite the reporter raising each time.
    assert process_attachment_mock.await_count == 2
    assert process_web_fetch_mock.await_count == 1
    assert reporter.item_calls == 3
    assert summary.banks_processed == 1
    # Stage 3 item B: commit is now per item (the reporter raises in the
    # finally AFTER each per-item commit). Each of the 3 items still committed,
    # and the progress-reporting failure must never trigger a rollback.
    assert session.commit.await_count == 3
    session.rollback.assert_not_awaited()
    # Swallow-with-log: failure is logged, not silent.
    assert "ingest progress reporting failed" in caplog.text
