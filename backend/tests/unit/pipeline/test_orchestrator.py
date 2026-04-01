"""Pipeline 協調器單元測試。

測試階段呼叫順序、容錯行為、摘要聚合。
"""

from unittest.mock import AsyncMock, patch

import pytest

from ccas.bot.job import NotifySummary
from ccas.classifier.job import ClassifySummary
from ccas.decryptor.job import DecryptionSummary
from ccas.ingestor.job import IngestionSummary
from ccas.parser.job import ParseSummary
from ccas.pipeline.orchestrator import run_pipeline


@pytest.fixture
def mock_session():
    return AsyncMock()


def _make_ingest_summary(**kwargs):
    defaults = {
        "banks_processed": 2,
        "messages_found": 3,
        "staged_count": 2,
        "skipped_count": 1,
        "failed_count": 0,
        "errors": [],
    }
    defaults.update(kwargs)
    return IngestionSummary(**defaults)


def _make_decrypt_summary(**kwargs):
    defaults = {
        "decrypted_count": 2,
        "passthrough_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "errors": [],
    }
    defaults.update(kwargs)
    return DecryptionSummary(**defaults)


def _make_parse_summary(**kwargs):
    defaults = {
        "parsed_count": 2,
        "skipped_count": 0,
        "failed_count": 0,
        "errors": [],
    }
    defaults.update(kwargs)
    return ParseSummary(**defaults)


def _make_classify_summary(**kwargs):
    defaults = {
        "classified_count": 10,
        "skipped_count": 0,
        "total_count": 10,
    }
    defaults.update(kwargs)
    return ClassifySummary(**defaults)


def _make_notify_summary(**kwargs):
    defaults = {
        "sent_count": 0,
        "failed_count": 0,
        "errors": [],
    }
    defaults.update(kwargs)
    return NotifySummary(**defaults)


class TestPipelineStageOrder:
    """5.1: 驗證 ingest -> decrypt -> parse -> classify -> notify 的呼叫順序。"""

    @pytest.mark.asyncio
    async def test_stages_called_in_order(self, mock_session):
        call_order = []

        async def mock_ingest(session, options=None):
            call_order.append("ingest")
            return _make_ingest_summary()

        async def mock_decrypt(session, options=None):
            call_order.append("decrypt")
            return _make_decrypt_summary()

        async def mock_parse(session, options=None):
            call_order.append("parse")
            return _make_parse_summary()

        async def mock_classify(session):
            call_order.append("classify")
            return _make_classify_summary()

        async def mock_notify(session, *, bill_ids=None):
            call_order.append("notify")
            return _make_notify_summary()

        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job", side_effect=mock_ingest
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                side_effect=mock_decrypt,
            ),
            patch("ccas.pipeline.orchestrator.run_parse_job", side_effect=mock_parse),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job", side_effect=mock_classify
            ),
            patch("ccas.pipeline.orchestrator.run_notify_job", side_effect=mock_notify),
        ):
            await run_pipeline(mock_session)

        assert call_order == ["ingest", "decrypt", "parse", "classify", "notify"]

    @pytest.mark.asyncio
    async def test_all_five_stages_present_in_summary(self, mock_session):
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(),
            ),
        ):
            summary = await run_pipeline(mock_session)

        stage_names = [s.stage for s in summary.stages]
        assert stage_names == ["ingest", "decrypt", "parse", "classify", "notify"]


class TestFaultTolerance:
    """5.2: 驗證單筆失敗不阻斷整批，且失敗項目不進入下一階段。"""

    @pytest.mark.asyncio
    async def test_partial_ingest_failure_doesnt_block_pipeline(self, mock_session):
        """Ingest 有失敗項目時，後續階段仍然被呼叫。"""
        stages_called = []

        async def mock_ingest(session, options=None):
            stages_called.append("ingest")
            return _make_ingest_summary(
                staged_count=1, failed_count=1, errors=["bank X failed"]
            )

        async def mock_decrypt(session, options=None):
            stages_called.append("decrypt")
            return _make_decrypt_summary()

        async def mock_parse(session, options=None):
            stages_called.append("parse")
            return _make_parse_summary()

        async def mock_classify(session):
            stages_called.append("classify")
            return _make_classify_summary()

        async def mock_notify(session, *, bill_ids=None):
            stages_called.append("notify")
            return _make_notify_summary()

        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job", side_effect=mock_ingest
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                side_effect=mock_decrypt,
            ),
            patch("ccas.pipeline.orchestrator.run_parse_job", side_effect=mock_parse),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job", side_effect=mock_classify
            ),
            patch("ccas.pipeline.orchestrator.run_notify_job", side_effect=mock_notify),
        ):
            summary = await run_pipeline(mock_session)

        assert len(stages_called) == 5
        # Ingest failures appear in summary
        ingest_stage = summary.stages[0]
        assert ingest_stage.counts["failed"] == 1
        assert len(ingest_stage.errors) == 1

    @pytest.mark.asyncio
    async def test_all_items_fail_in_stage_subsequent_stages_still_run(
        self, mock_session
    ):
        """某階段全部失敗時，後續階段仍被呼叫（空跑）。"""
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(staged_count=0, failed_count=3),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(decrypted_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(parsed_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(classified_count=0, total_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(),
            ),
        ):
            summary = await run_pipeline(mock_session)

        # All 5 stages still present
        assert len(summary.stages) == 5
        # All counts are zero for downstream stages
        assert summary.stages[1].counts["decrypted"] == 0
        assert summary.stages[2].counts["parsed"] == 0
        assert summary.stages[3].counts["classified"] == 0


class TestSummaryAggregation:
    """5.3: 驗證各階段統計數字正確反映處理結果。"""

    @pytest.mark.asyncio
    async def test_summary_counts_match_stage_results(self, mock_session):
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(
                    staged_count=3, skipped_count=1, failed_count=1
                ),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(decrypted_count=2, failed_count=1),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(parsed_count=2, failed_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(classified_count=15),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(
                    sent_count=2, failed_count=1, errors=["notify err"]
                ),
            ),
        ):
            summary = await run_pipeline(mock_session)

        assert summary.stages[0].counts == {"staged": 3, "skipped": 1, "failed": 1}
        assert summary.stages[1].counts == {
            "decrypted": 2,
            "passthrough": 0,
            "failed": 1,
        }
        assert summary.stages[2].counts == {"parsed": 2, "skipped": 0, "failed": 0}
        assert summary.stages[3].counts == {"classified": 15}
        assert summary.stages[4].counts == {"sent": 2, "failed": 1}

    @pytest.mark.asyncio
    async def test_total_seconds_is_positive(self, mock_session):
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(),
            ),
        ):
            summary = await run_pipeline(mock_session)

        assert summary.total_seconds >= 0

    @pytest.mark.asyncio
    async def test_failures_collected_from_all_stages(self, mock_session):
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(errors=["ingest err"]),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(errors=["decrypt err"]),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(errors=["parse err"]),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(errors=["notify err"]),
            ),
        ):
            summary = await run_pipeline(mock_session)

        assert len(summary.failures) == 4
        stages_in_failures = {f.item_id.split(":")[0] for f in summary.failures}
        assert stages_in_failures == {"ingest", "decrypt", "parse", "notify"}

    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_zero_counts(self, mock_session):
        """無任何資料時，所有階段計數為零，摘要仍完整。"""
        with (
            patch(
                "ccas.pipeline.orchestrator.run_ingestion_job",
                return_value=_make_ingest_summary(banks_processed=0, staged_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_decryption_job",
                return_value=_make_decrypt_summary(decrypted_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_parse_job",
                return_value=_make_parse_summary(parsed_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_classify_job",
                return_value=_make_classify_summary(classified_count=0, total_count=0),
            ),
            patch(
                "ccas.pipeline.orchestrator.run_notify_job",
                return_value=_make_notify_summary(),
            ),
        ):
            summary = await run_pipeline(mock_session)

        assert len(summary.stages) == 5
        assert summary.failures == ()
