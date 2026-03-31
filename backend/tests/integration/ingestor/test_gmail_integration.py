"""Gmail 整合測試：使用 mocked Gmail API 測試完整下載流程。"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage
from ccas.ingestor.job import run_ingestion_job
from ccas.storage.models import BankConfig, Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")
os.environ.setdefault("API_TOKEN", "test")


@pytest.fixture
async def db_session():
    """提供 in-memory SQLite 的 AsyncSession。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _sample_message(
    message_id="msg-001",
    filename="bill.pdf",
    attachment_id="att-001",
):
    """建立測試用 GmailMessage。"""
    return GmailMessage(
        message_id=message_id,
        message_date=datetime(2026, 3, 10),
        pdf_attachments=(
            GmailAttachmentMeta(
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
                message_date=datetime(2026, 3, 10),
                size=1024,
            ),
        ),
    )


async def _seed_bank(session, bank_code="CTBC", is_active=True):
    """寫入測試用銀行設定。"""
    config = BankConfig(
        bank_code=bank_code,
        bank_name=f"Test Bank {bank_code}",
        gmail_filter=f"from:{bank_code.lower()}@example.com",
        is_active=is_active,
    )
    session.add(config)
    await session.flush()


class TestSuccessfulDownload:
    """成功下載 PDF 附件的整合測試。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_creates_staged_record(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """成功下載後 DB 中有一筆 status='staged' 的記錄。"""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            await _seed_bank(session, "CTBC")
            await session.commit()

            settings = MagicMock()
            settings.gmail_credentials_path = "/fake/creds.json"
            settings.gmail_token_path = "/fake/token.json"
            settings.staging_dir = "/tmp/test_staging"
            mock_settings.return_value = settings

            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            # mock asyncio.to_thread for search/download/write
            call_count = {"n": 0}

            async def fake_to_thread(fn, *args):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # search_messages
                    return [_sample_message()]
                if call_count["n"] == 2:
                    # download_attachment
                    return b"fake-pdf-content"
                # mkdir or write_bytes
                return None

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_ingestion_job(session)

            assert summary.staged_count == 1
            assert summary.failed_count == 0

            stmt = select(StagedAttachment)
            result = await session.execute(stmt)
            records = result.scalars().all()
            assert len(records) == 1
            assert records[0].status == "staged"
            assert records[0].bank_code == "CTBC"

        await engine.dispose()


class TestDownloadFailure:
    """下載失敗的整合測試。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_creates_failed_record(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """下載失敗後 DB 中有一筆 status='failed' 且 error_reason 非空。"""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            await _seed_bank(session, "CTBC")
            await session.commit()

            settings = MagicMock()
            settings.gmail_credentials_path = "/fake/creds.json"
            settings.gmail_token_path = "/fake/token.json"
            settings.staging_dir = "/tmp/test_staging"
            mock_settings.return_value = settings

            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            call_count = {"n": 0}

            async def fake_to_thread(fn, *args):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return [_sample_message()]
                if call_count["n"] == 2:
                    raise RuntimeError("Network timeout")
                return None

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_ingestion_job(session)

            assert summary.staged_count == 0
            assert summary.failed_count == 1
            assert len(summary.errors) == 1

            stmt = select(StagedAttachment)
            result = await session.execute(stmt)
            records = result.scalars().all()
            assert len(records) == 1
            assert records[0].status == "failed"
            assert records[0].error_reason is not None

        await engine.dispose()
