"""Force replacement safety for the shared staged-source lifecycle."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.gmail_client import GmailAttachmentMeta
from ccas.ingestor.job import _process_attachment
from ccas.ingestor.lifecycle import StagingDisposition
from ccas.storage.models import Base, StagedAttachment


@pytest.fixture
def attachment() -> GmailAttachmentMeta:
    return GmailAttachmentMeta(
        message_id="msg123",
        attachment_id="att456",
        filename="statement.pdf",
        message_date=datetime(2026, 3, 15),
        size=1024,
        part_id="1",
    )


async def _create_attachment_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _seed_existing(session: AsyncSession, attachment: GmailAttachmentMeta) -> int:
    existing = StagedAttachment(
        bank_code="CTBC",
        gmail_message_id=attachment.message_id,
        gmail_attachment_id=attachment.attachment_id,
        gmail_part_id=attachment.part_id,
        message_date=attachment.message_date,
        original_filename=attachment.filename,
        staged_path="legacy/previous.pdf",
        status="staged",
    )
    session.add(existing)
    await session.commit()
    return existing.id


class TestForceModeSafety:
    async def test_force_download_failure_preserves_old_file_and_path(
        self,
        attachment: GmailAttachmentMeta,
        tmp_path: Path,
    ) -> None:
        engine, factory = await _create_attachment_test_db()
        old_file = tmp_path / "legacy/previous.pdf"
        old_file.parent.mkdir(parents=True)
        old_file.write_bytes(b"previous committed PDF")

        async with factory() as session:
            existing_id = await _seed_existing(session, attachment)
            with patch(
                "ccas.ingestor.job.download_attachment",
                side_effect=RuntimeError("download failed"),
            ):
                result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                    force=True,
                )

            assert result.disposition == StagingDisposition.FAILED
            existing = await session.get(StagedAttachment, existing_id)
            assert existing is not None
            assert existing.staged_path == "legacy/previous.pdf"
            assert existing.status == "failed"
            assert old_file.read_bytes() == b"previous committed PDF"

        await engine.dispose()

    async def test_non_force_download_failure_persists_failed_result(
        self,
        attachment: GmailAttachmentMeta,
        tmp_path: Path,
    ) -> None:
        engine, factory = await _create_attachment_test_db()
        async with factory() as session:
            with patch(
                "ccas.ingestor.job.download_attachment",
                side_effect=RuntimeError("download failed"),
            ):
                result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                )

            assert result.disposition == StagingDisposition.FAILED
            record = await session.scalar(select(StagedAttachment))
            assert record is not None
            assert record.status == "failed"
            assert record.staged_path is None

        await engine.dispose()


class TestProcessAttachmentRetryNoDelete:
    async def test_force_retry_same_path_preserves_file(
        self,
        tmp_path: Path,
    ) -> None:
        """A force retry to the same storage path must keep the new PDF."""
        engine, factory = await _create_attachment_test_db()
        fake_pdf = b"%PDF-1.4 fake"
        attachment = GmailAttachmentMeta(
            message_id="msg-att-force",
            attachment_id="att-001",
            filename="statement.pdf",
            message_date=datetime(2026, 3, 15),
            size=len(fake_pdf),
            part_id="1",
        )

        async with factory() as session:
            with patch("ccas.ingestor.job.download_attachment", return_value=fake_pdf):
                first_result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                )
            assert first_result.disposition == StagingDisposition.STAGED

            with patch("ccas.ingestor.job.download_attachment", return_value=fake_pdf):
                retry_result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                    force=True,
                )
            assert retry_result.disposition == StagingDisposition.STAGED

            pdf_files = list(tmp_path.rglob("*.pdf"))
            assert len(pdf_files) == 1
            assert pdf_files[0].read_bytes() == fake_pdf
            record = await session.scalar(select(StagedAttachment))
            assert record is not None
            assert record.staged_path is not None

        await engine.dispose()
