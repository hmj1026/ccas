"""Force mode safety tests for ingestor job.

Verifies that force mode preserves existing data when download fails
and only cleans up after successful download.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.gmail_client import GmailAttachmentMeta
from ccas.ingestor.job import IngestionSummary, _process_attachment
from ccas.storage.models import Base


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
def existing_record():
    record = MagicMock()
    record.staged_path = "/data/staged/CTBC/msg123_statement.pdf"
    return record


@pytest.fixture
def summary():
    from ccas.ingestor.job import IngestionSummary

    return IngestionSummary()


class TestForceModeSafety:
    @patch("ccas.ingestor.job.download_attachment", side_effect=Exception("API error"))
    @patch("ccas.ingestor.job.delete_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job._cleanup_old_staged_file", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    async def test_force_download_failure_preserves_old_record(
        self,
        mock_create,
        mock_find,
        mock_cleanup,
        mock_delete,
        mock_download,
        attachment,
        existing_record,
        summary,
    ):
        """When force download fails, old record and file must remain intact."""
        mock_find.return_value = existing_record
        session = AsyncMock()

        await _process_attachment(
            session,
            MagicMock(),
            "CTBC",
            attachment,
            "/data/staged",
            summary,
            force=True,
        )

        # Old record must NOT be deleted
        mock_cleanup.assert_not_called()
        mock_delete.assert_not_called()

        # No new "failed" record should be created (old record preserved)
        mock_create.assert_not_called()

        # Error should still be tracked in summary
        assert summary.failed_count == 1
        assert len(summary.errors) == 1
        assert "API error" in summary.errors[0]

    @patch("ccas.ingestor.job.download_attachment", return_value=b"pdf-bytes")
    @patch("ccas.ingestor.job.delete_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job._cleanup_old_staged_file", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.build_staged_path")
    async def test_force_download_success_cleans_up_old_record(
        self,
        mock_build_path,
        mock_create,
        mock_find,
        mock_cleanup,
        mock_delete,
        mock_download,
        attachment,
        existing_record,
        summary,
    ):
        """When force download succeeds, old record and file should be cleaned up."""
        mock_find.return_value = existing_record
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
            force=True,
        )

        # Old record should be cleaned up after download success
        mock_cleanup.assert_called_once_with(
            "/data/staged", existing_record.staged_path
        )
        mock_delete.assert_called_once_with(session, existing_record)

        # New record should be created
        mock_create.assert_called_once()
        assert summary.staged_count == 1

    @patch("ccas.ingestor.job.download_attachment", side_effect=Exception("fail"))
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    async def test_non_force_download_failure_creates_failed_record(
        self,
        mock_create,
        mock_find,
        mock_download,
        attachment,
        summary,
    ):
        """Without force mode, download failure should create a failed record."""
        mock_find.return_value = None
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

        # Failed record should be created (no existing record to preserve)
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs.get("status") == "failed" or (
            len(call_kwargs.args) == 0 and "failed" in str(call_kwargs)
        )
        assert summary.failed_count == 1


async def _create_attachment_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


class TestProcessAttachmentRetryNoDelete:
    """_process_attachment: force retry to the same path must not delete the new file."""

    async def test_force_retry_same_path_preserves_file(self, tmp_path: Path):
        """When force=True downloads to the identical staged path, the file must survive."""
        engine, factory = await _create_attachment_test_db()
        _FAKE_PDF = b"%PDF-1.4 fake"

        def fake_download(service, message_id, attachment_id):
            return _FAKE_PDF

        attachment = GmailAttachmentMeta(
            message_id="msg-att-force",
            attachment_id="att-001",
            filename="statement.pdf",
            message_date=datetime(2026, 3, 15),
            size=len(_FAKE_PDF),
            part_id="1",
        )

        async with factory() as session:
            # First call: stage the file normally
            with patch("ccas.ingestor.job.download_attachment", side_effect=fake_download):
                await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                    IngestionSummary(),
                )
            await session.commit()

            pdf_files = list(tmp_path.rglob("*.pdf"))
            assert len(pdf_files) == 1

            # Second call with force=True: same message_id + filename → same staged path
            second_summary = IngestionSummary()
            with patch("ccas.ingestor.job.download_attachment", side_effect=fake_download):
                await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                    second_summary,
                    force=True,
                )
            await session.commit()

            # File must still be on disk and contain valid content
            pdf_files = list(tmp_path.rglob("*.pdf"))
            assert len(pdf_files) == 1
            assert pdf_files[0].read_bytes() == _FAKE_PDF
            assert second_summary.staged_count == 1

        await engine.dispose()
