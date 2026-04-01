"""Pipeline orchestrator options forwarding tests.

Verifies that PipelineOptions are correctly passed to ingestion and parse stages.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ccas.bot.job import NotifySummary
from ccas.classifier.job import ClassifySummary
from ccas.decryptor.job import DecryptionSummary
from ccas.ingestor.job import IngestionSummary
from ccas.parser.job import ParseSummary
from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.orchestrator import run_pipeline


@pytest.fixture
def mock_session():
    return AsyncMock()


def _patch_all_stages():
    """Patch all 5 pipeline stages with return_value mocks."""
    return (
        patch(
            "ccas.pipeline.orchestrator.run_ingestion_job",
            new_callable=AsyncMock,
            return_value=IngestionSummary(),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_decryption_job",
            new_callable=AsyncMock,
            return_value=DecryptionSummary(),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_parse_job",
            new_callable=AsyncMock,
            return_value=ParseSummary(),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_classify_job",
            new_callable=AsyncMock,
            return_value=ClassifySummary(
                classified_count=0, skipped_count=0, total_count=0
            ),
        ),
        patch(
            "ccas.pipeline.orchestrator.run_notify_job",
            new_callable=AsyncMock,
            return_value=NotifySummary(),
        ),
    )


class TestOptionsForwarding:
    async def test_options_passed_to_ingest_and_parse(self, mock_session):
        options = PipelineOptions(force=True, bank_code="CTBC")

        p_ingest, p_decrypt, p_parse, p_classify, p_notify = _patch_all_stages()
        with p_ingest as m_ingest, p_decrypt, p_parse as m_parse, p_classify, p_notify:
            await run_pipeline(mock_session, options)

            m_ingest.assert_called_once_with(mock_session, options)
            m_parse.assert_called_once_with(mock_session, options)

    async def test_none_options_passed_by_default(self, mock_session):
        p_ingest, p_decrypt, p_parse, p_classify, p_notify = _patch_all_stages()
        with p_ingest as m_ingest, p_decrypt, p_parse as m_parse, p_classify, p_notify:
            await run_pipeline(mock_session)

            m_ingest.assert_called_once_with(mock_session, None)
            m_parse.assert_called_once_with(mock_session, None)

    async def test_decrypt_receives_options(self, mock_session):
        """Decrypt should receive options for bank/date filtering."""
        options = PipelineOptions(force=True, bank_code="CTBC")

        p_ingest, p_decrypt, p_parse, p_classify, p_notify = _patch_all_stages()
        with (
            p_ingest,
            p_decrypt as m_dec,
            p_parse,
            p_classify,
            p_notify,
        ):
            await run_pipeline(mock_session, options)

            m_dec.assert_called_once_with(mock_session, options)

    async def test_classify_notify_unaffected(self, mock_session):
        """Classify and notify should NOT receive options."""
        options = PipelineOptions(force=True)

        p_ingest, p_decrypt, p_parse, p_classify, p_notify = _patch_all_stages()
        with (
            p_ingest,
            p_decrypt,
            p_parse,
            p_classify as m_cls,
            p_notify as m_ntf,
        ):
            await run_pipeline(mock_session, options)

            m_cls.assert_called_once_with(mock_session)
            m_ntf.assert_called_once_with(mock_session)
