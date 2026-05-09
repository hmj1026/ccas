"""Failed 附件自動重試測試。

驗證 status="failed" 的既有記錄在下次執行時自動重試，
status="staged" 的記錄仍然被 skip。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.ingestor.gmail_client import GmailAttachmentMeta
from ccas.ingestor.job import IngestionSummary, _process_attachment


@pytest.fixture
def attachment():
    return GmailAttachmentMeta(
        message_id="msg123",
        attachment_id="att456",
        filename="statement.pdf",
        message_date=datetime(2026, 3, 15),
        size=1024,
    )


@pytest.fixture
def summary():
    return IngestionSummary()


class TestFailedRetry:
    """status='failed' 記錄應自動重試。"""

    @patch("ccas.ingestor.job.download_attachment", return_value=b"pdf-bytes")
    @patch("ccas.ingestor.job.delete_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job._cleanup_old_staged_file", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.build_staged_path")
    async def test_failed_record_triggers_retry(
        self,
        mock_build_path,
        mock_create,
        mock_find,
        mock_cleanup,
        mock_delete,
        mock_download,
        attachment,
        summary,
    ):
        """status='failed' 的記錄不應被 skip，應進入重新下載流程。"""
        existing = MagicMock()
        existing.status = "failed"
        existing.staged_path = None
        mock_find.return_value = existing

        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build_path.return_value = mock_path

        session = AsyncMock()

        await _process_attachment(
            session,
            MagicMock(),
            "CTBC",
            attachment,
            "/data/staged",
            summary,
            force=False,
        )

        # Should NOT be skipped
        assert summary.skipped_count == 0
        # Should download and create new record
        assert summary.staged_count == 1
        mock_download.assert_called_once()
        mock_create.assert_called_once()


class TestStagedSkip:
    """status='staged' 記錄應正常 skip（回歸保護）。"""

    @patch("ccas.ingestor.job.download_attachment")
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    async def test_staged_record_is_skipped(
        self,
        mock_find,
        mock_download,
        attachment,
        summary,
    ):
        """status='staged' 的記錄應被 skip，不重新下載。"""
        existing = MagicMock()
        existing.status = "staged"
        mock_find.return_value = existing

        session = AsyncMock()

        await _process_attachment(
            session,
            MagicMock(),
            "CTBC",
            attachment,
            "/data/staged",
            summary,
            force=False,
        )

        assert summary.skipped_count == 1
        assert summary.staged_count == 0
        mock_download.assert_not_called()
