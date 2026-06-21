"""Ingestion job 層級的整合測試：多銀行處理與 batch summary。"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage
from ccas.ingestor.job import (
    IngestionSummary,
    _process_attachment,
    run_ingestion_job,
)
from ccas.ingestor.staging import create_staged_record
from ccas.storage.models import (
    BankConfig,
    Base,
    StagedAttachment,
    StagedAttachmentStatus,
)

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test")


def _sample_message(
    message_id="msg-001",
    filename="bill.pdf",
    attachment_id="att-001",
):
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


async def _create_test_session():
    """建立 in-memory DB + session。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


def _mock_settings():
    settings = MagicMock()
    settings.gmail_credentials_path = "/fake/creds.json"
    settings.gmail_token_path = "/fake/token.json"
    settings.staging_dir = "/tmp/test_staging"
    return settings


class TestMultiBankProcessing:
    """多銀行處理的測試案例。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_processes_all_active_banks(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """所有啟用中的銀行都被處理。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            for code in ("CTBC", "CATHAY"):
                session.add(
                    BankConfig(
                        bank_code=code,
                        bank_name=f"Bank {code}",
                        gmail_filter=f"from:{code.lower()}@example.com",
                        is_active=True,
                    )
                )
            await session.commit()

            mock_settings.return_value = _mock_settings()
            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            call_count = {"n": 0}

            # Per bank: search(1) + download(1) + mkdir(1) + write(1) = 4
            # Bank1: calls 1-4, Bank2: calls 5-8
            async def fake_to_thread(fn, *args, **kwargs):
                call_count["n"] += 1
                n = call_count["n"]
                if n in (1, 5):
                    return [
                        _sample_message(
                            f"msg-{n}",
                            "bill.pdf",
                            f"att-{n}",
                        )
                    ]
                if n in (2, 6):
                    return b"fake-pdf"
                return None

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_ingestion_job(session)
            assert summary.banks_processed == 2

        await engine.dispose()

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_inactive_bank_skipped(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """未啟用的銀行不被處理。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="INACTIVE",
                    bank_name="Inactive Bank",
                    gmail_filter="from:inactive@example.com",
                    is_active=False,
                )
            )
            await session.commit()

            mock_settings.return_value = _mock_settings()
            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            summary = await run_ingestion_job(session)
            assert summary.banks_processed == 0
            mock_to_thread.assert_not_called()

        await engine.dispose()


class TestBatchSummary:
    """Batch summary 統計的測試案例。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_summary_counts(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """驗證 summary 的 staged/skipped/failed 計數。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="CTBC",
                    bank_name="CTBC",
                    gmail_filter="from:ctbc@example.com",
                    is_active=True,
                )
            )
            # 預先插入一筆 staged record 以觸發 dedupe skip
            session.add(
                StagedAttachment(
                    bank_code="CTBC",
                    gmail_message_id="msg-existing",
                    gmail_attachment_id="att-existing",
                    message_date=datetime(2026, 3, 1),
                    original_filename="old.pdf",
                    staged_path="/data/staging/CTBC/old.pdf",
                    status="staged",
                )
            )
            await session.commit()

            mock_settings.return_value = _mock_settings()
            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            call_count = {"n": 0}

            async def fake_to_thread(fn, *args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # search_messages: 3 messages, 1 existing + 1 success + 1 fail
                    return [
                        _sample_message("msg-existing", "old.pdf", "att-existing"),
                        _sample_message("msg-new", "new.pdf", "att-new"),
                        _sample_message("msg-fail", "fail.pdf", "att-fail"),
                    ]
                if call_count["n"] == 2:
                    # download for msg-new
                    return b"fake-pdf"
                if call_count["n"] == 3:
                    # mkdir for msg-new
                    return None
                if call_count["n"] == 4:
                    # write_bytes for msg-new
                    return None
                if call_count["n"] == 5:
                    # download for msg-fail
                    raise RuntimeError("Download failed")
                return None

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_ingestion_job(session)

            assert summary.staged_count == 1
            assert summary.skipped_count == 1
            assert summary.failed_count == 1
            assert summary.messages_found == 3

        await engine.dispose()


class TestFaultTolerance:
    """單筆失敗不中止整批的測試案例。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_bank_search_failure_continues_others(
        self, mock_settings, mock_load_creds, mock_build_service, mock_to_thread
    ):
        """某家銀行搜尋失敗，其他銀行仍正常處理。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            for code in ("FAIL_BANK", "OK_BANK"):
                session.add(
                    BankConfig(
                        bank_code=code,
                        bank_name=f"Bank {code}",
                        gmail_filter=f"from:{code.lower()}@example.com",
                        is_active=True,
                    )
                )
            await session.commit()

            mock_settings.return_value = _mock_settings()
            mock_load_creds.return_value = MagicMock()
            mock_build_service.return_value = MagicMock()

            call_count = {"n": 0}

            async def fake_to_thread(fn, *args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # FAIL_BANK search fails
                    raise RuntimeError("Gmail API error for FAIL_BANK")
                if call_count["n"] == 2:
                    # OK_BANK search succeeds
                    return [_sample_message("msg-ok", "bill.pdf", "att-ok")]
                if call_count["n"] == 3:
                    # download
                    return b"fake-pdf"
                return None

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_ingestion_job(session)

            assert summary.banks_processed == 2
            assert summary.staged_count == 1
            assert len(summary.errors) >= 1

            stmt = select(StagedAttachment).where(
                StagedAttachment.bank_code == "OK_BANK"
            )
            result = await session.execute(stmt)
            ok_records = result.scalars().all()
            assert len(ok_records) == 1

        await engine.dispose()


class TestRetryFailureUpdatesErrorReason:
    """重試 failed 附件再失敗時，須更新既有紀錄的 error_reason（與 web-fetch 對稱）。"""

    async def test_retry_failure_overwrites_stale_error_reason(self):
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            # 既有 failed 紀錄，帶舊的 error_reason。
            existing = await create_staged_record(
                session,
                bank_code="UBOT",
                message_id="msg-retry",
                attachment_id="att-old",
                message_date=datetime(2026, 3, 10),
                original_filename="bill.pdf",
                staged_path=None,
                status=StagedAttachmentStatus.FAILED,
                error_reason="OLD stale reason",
                part_id="1",
            )
            await session.commit()
            existing_id = existing.id

            attachment = GmailAttachmentMeta(
                message_id="msg-retry",
                attachment_id="att-new",
                filename="bill.pdf",
                message_date=datetime(2026, 3, 10),
                size=1024,
                part_id="1",
            )
            summary = IngestionSummary()

            # 重試下載再次失敗。
            async def fail_to_thread(fn, *args, **kwargs):
                raise RuntimeError("NEW download timeout")

            with patch(
                "ccas.ingestor.job.asyncio.to_thread", side_effect=fail_to_thread
            ):
                ret = await _process_attachment(
                    session,
                    MagicMock(),
                    "UBOT",
                    attachment,
                    "/tmp/test_staging",
                    summary,
                )

            assert ret is None
            assert summary.failed_count == 1

            stmt = select(StagedAttachment).where(StagedAttachment.id == existing_id)
            record = (await session.execute(stmt)).scalar_one()
            # 不殘留舊原因；更新為最新失敗原因。
            assert record.status == StagedAttachmentStatus.FAILED
            assert "NEW download timeout" in (record.error_reason or "")
            assert "OLD stale reason" not in (record.error_reason or "")

            # 未新增重複紀錄。
            all_rows = (await session.execute(select(StagedAttachment))).scalars().all()
            assert len(all_rows) == 1

        await engine.dispose()
