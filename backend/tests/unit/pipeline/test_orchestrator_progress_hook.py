"""Orchestrator ProgressReporter 注入點測試（pipeline-operations-center §3.7）。

涵蓋：
- ``run_pipeline`` 不傳 ``progress_reporter`` 時內部包成 NoopReporter，CLI
  / scheduler 路徑行為不變
- 顯式注入 fake reporter 時，``stage_finished`` 對每個執行的階段呼叫一次
- 階段內 exception 時 ``stage_finished`` 仍以當下統計（fail=1）發出
  （spec §3.5）
- ``ok`` / ``fail`` 計算正確：fail = counts['failed']，ok = sum(counts) - fail
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from ccas.bot.job import NotifySummary
from ccas.classifier.job import ClassifySummary
from ccas.decryptor.job import DecryptionSummary
from ccas.ingestor.job import IngestionSummary
from ccas.parser.job import ParseSummary
from ccas.pipeline.orchestrator import run_pipeline

from .conftest import FakeReporter


def _patches(**stage_returns: Any):
    return [
        patch(
            "ccas.pipeline.orchestrator.run_ingestion_job",
            return_value=stage_returns.get(
                "ingest",
                IngestionSummary(
                    banks_processed=1,
                    messages_found=2,
                    staged_count=2,
                    skipped_count=0,
                    failed_count=0,
                    errors=[],
                ),
            ),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_decryption_job",
            return_value=stage_returns.get(
                "decrypt",
                DecryptionSummary(
                    decrypted_count=2,
                    passthrough_count=0,
                    skipped_count=0,
                    failed_count=0,
                    errors=[],
                ),
            ),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_parse_job",
            return_value=stage_returns.get(
                "parse",
                ParseSummary(
                    parsed_count=2,
                    skipped_count=0,
                    failed_count=0,
                    errors=[],
                ),
            ),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_classify_job",
            return_value=stage_returns.get(
                "classify",
                ClassifySummary(
                    classified_count=10,
                    skipped_count=0,
                    total_count=10,
                ),
            ),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_notify_job",
            return_value=stage_returns.get(
                "notify",
                NotifySummary(sent_count=1, failed_count=0, errors=[]),
            ),
        ),
    ]


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


async def test_default_reporter_is_noop(mock_session: AsyncMock) -> None:
    """run_pipeline 不傳 reporter 時走 Noop，stdout summary 行為不變。"""
    with (
        _patches()[0],
        _patches()[1],
        _patches()[2],
        _patches()[3],
        _patches()[4],
    ):
        summary = await run_pipeline(mock_session)

    # All five stages present; no reporter side-effect to inspect, just no
    # exception means Noop wrapping worked.
    assert [s.stage for s in summary.stages] == [
        "ingest",
        "decrypt",
        "parse",
        "classify",
        "notify",
    ]


async def test_fake_reporter_receives_one_stage_finished_per_stage(
    mock_session: AsyncMock,
) -> None:
    reporter = FakeReporter()

    patches = _patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await run_pipeline(mock_session, progress_reporter=reporter)

    finished_stages = [
        c[1]["stage"] for c in reporter.calls if c[0] == "stage_finished"
    ]
    assert finished_stages == [
        "ingest",
        "decrypt",
        "parse",
        "classify",
        "notify",
    ]


async def test_stage_finished_ok_fail_split_excludes_failed_bucket(
    mock_session: AsyncMock,
) -> None:
    """ok = sum(counts) - failed; fail = counts['failed']."""
    reporter = FakeReporter()

    parse_with_fail = ParseSummary(
        parsed_count=8,
        skipped_count=1,
        failed_count=2,
        errors=["e1", "e2"],
    )
    patches = _patches(parse=parse_with_fail)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await run_pipeline(mock_session, progress_reporter=reporter)

    parse_finished = next(
        c
        for c in reporter.calls
        if c[0] == "stage_finished" and c[1]["stage"] == "parse"
    )
    # 8 parsed + 1 skipped = 9 ok; 2 failed.
    assert parse_finished[1]["ok"] == 9
    assert parse_finished[1]["fail"] == 2


async def test_stage_exception_still_emits_stage_finished(
    mock_session: AsyncMock,
) -> None:
    """spec §3.5: 階段內 raise 時 stage_finished 仍須帶當下統計（fail=1）發出。"""
    reporter = FakeReporter()

    async def parse_boom(*args: Any, **kwargs: Any) -> ParseSummary:
        raise RuntimeError("parse exploded")

    with (
        _patches()[0],
        _patches()[1],
        patch("ccas.pipeline.orchestrator.run_parse_job", side_effect=parse_boom),
        _patches()[3],
        _patches()[4],
    ):
        summary = await run_pipeline(mock_session, progress_reporter=reporter)

    finished = [c[1] for c in reporter.calls if c[0] == "stage_finished"]
    parse_finished = next(c for c in finished if c["stage"] == "parse")
    assert parse_finished["fail"] == 1
    assert parse_finished["ok"] == 0
    # All five stages still ran (orchestrator does not abort).
    assert [c["stage"] for c in finished] == [
        "ingest",
        "decrypt",
        "parse",
        "classify",
        "notify",
    ]
    # parse summary records the failure.
    parse_ss = next(s for s in summary.stages if s.stage == "parse")
    assert parse_ss.counts.get("failed") == 1
    assert parse_ss.errors == ["RuntimeError: parse exploded"]


async def test_stage_finished_elapsed_ms_non_negative(
    mock_session: AsyncMock,
) -> None:
    reporter = FakeReporter()

    patches = _patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await run_pipeline(mock_session, progress_reporter=reporter)

    elapsed_values = [
        c[1]["elapsed_ms"] for c in reporter.calls if c[0] == "stage_finished"
    ]
    assert all(v >= 0 for v in elapsed_values)
    assert len(elapsed_values) == 5


async def test_partial_stage_range_emits_finished_only_for_run_stages(
    mock_session: AsyncMock,
) -> None:
    """from_stage=parse, to_stage=classify → only 2 stage_finished events."""
    from ccas.pipeline.options import PipelineOptions

    reporter = FakeReporter()
    options = PipelineOptions(from_stage="parse", to_stage="classify")

    patches = _patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await run_pipeline(mock_session, options=options, progress_reporter=reporter)

    finished_stages = [
        c[1]["stage"] for c in reporter.calls if c[0] == "stage_finished"
    ]
    assert finished_stages == ["parse", "classify"]
