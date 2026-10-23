"""Failed staged-source records retry; completed records remain deduplicated."""

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


async def _create_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _seed_record(
    session: AsyncSession,
    attachment: GmailAttachmentMeta,
    *,
    status: str,
) -> None:
    session.add(
        StagedAttachment(
            bank_code="CTBC",
            gmail_message_id=attachment.message_id,
            gmail_attachment_id=attachment.attachment_id,
            gmail_part_id=attachment.part_id,
            message_date=attachment.message_date,
            original_filename=attachment.filename,
            staged_path=None,
            status=status,
        )
    )
    await session.commit()


class TestFailedRetry:
    async def test_failed_record_is_retried_and_staged(
        self,
        attachment: GmailAttachmentMeta,
        tmp_path: Path,
    ) -> None:
        engine, factory = await _create_db()
        async with factory() as session:
            await _seed_record(session, attachment, status="failed")
            with patch(
                "ccas.ingestor.job.download_attachment", return_value=b"%PDF retry"
            ) as download:
                result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                )

            assert result.disposition == StagingDisposition.STAGED
            download.assert_called_once()
            record = await session.scalar(select(StagedAttachment))
            assert record is not None
            assert record.status == "staged"
            assert record.staged_path is not None
            assert (tmp_path / record.staged_path).read_bytes() == b"%PDF retry"

        await engine.dispose()


class TestStagedSkip:
    async def test_staged_record_is_skipped_without_download(
        self,
        attachment: GmailAttachmentMeta,
        tmp_path: Path,
    ) -> None:
        engine, factory = await _create_db()
        async with factory() as session:
            await _seed_record(session, attachment, status="staged")
            with patch("ccas.ingestor.job.download_attachment") as download:
                result = await _process_attachment(
                    session,
                    MagicMock(),
                    "CTBC",
                    attachment,
                    str(tmp_path),
                )

            assert result.disposition == StagingDisposition.SKIPPED
            download.assert_not_called()

        await engine.dispose()
