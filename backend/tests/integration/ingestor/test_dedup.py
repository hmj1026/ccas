"""Integration test: ingest dedup via stable Gmail MIME part_id.

模擬 Gmail API 在不同呼叫中回傳不同 attachment_id 但相同 part_id 的實務行為，
驗證 ingest 階段第二次執行應完整 skip。
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage
from ccas.ingestor.job import run_ingestion_job
from ccas.storage.models import BankConfig, Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test")


async def _create_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _mock_settings(staging_dir: str):
    settings = MagicMock()
    settings.gmail_credentials_path = "/fake/creds.json"
    settings.gmail_token_path = "/fake/token.json"
    settings.staging_dir = staging_dir
    return settings


def _message_with(attachment_id: str) -> GmailMessage:
    """Construct a GmailMessage whose single PDF attachment mimics Gmail's
    behaviour: ``attachmentId`` is regenerated on each API call (we vary it),
    but ``partId`` remains ``"1"`` because the MIME structure is unchanged.
    """
    return GmailMessage(
        message_id="msg-STABLE",
        message_date=datetime(2026, 3, 10),
        pdf_attachments=(
            GmailAttachmentMeta(
                message_id="msg-STABLE",
                attachment_id=attachment_id,
                filename="bill.pdf",
                message_date=datetime(2026, 3, 10),
                size=1024,
                part_id="1",
            ),
        ),
    )


class TestIngestDedupeStability:
    """驗證 Gmail attachment_id 旋轉不影響 dedupe。"""

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_second_run_skips_when_attachment_id_rotated(
        self,
        mock_get_settings,
        mock_load_creds,
        mock_build_service,
        mock_to_thread,
    ):
        """第一次 ingest 後，attachment_id 旋轉，第二次仍應完全 skip。"""
        engine, factory = await _create_test_session()
        with tempfile.TemporaryDirectory() as tmp:
            async with factory() as session:
                session.add(
                    BankConfig(
                        bank_code="CTBC",
                        bank_name="CTBC",
                        gmail_filter="from:ctbc@example.com",
                        is_active=True,
                    )
                )
                await session.commit()

                mock_get_settings.return_value = _mock_settings(tmp)
                mock_load_creds.return_value = MagicMock()
                mock_build_service.return_value = MagicMock()

                # Run 1: Gmail returns attachment_id="att-A1" / part_id="1"
                # Run 2: Gmail returns attachment_id="att-A2" / part_id="1"
                run_state = {"run": 1, "n": 0}

                async def fake_to_thread(fn, *args, **kwargs):
                    run_state["n"] += 1
                    n = run_state["n"]
                    # First call in each run: search_messages
                    if n in (1, 5):
                        att_id = "att-A1" if run_state["run"] == 1 else "att-A2"
                        return [_message_with(att_id)]
                    # Second call: download_attachment -> bytes
                    if n in (2, 6):
                        return b"fake-pdf-bytes"
                    # Subsequent calls: mkdir / write -> None
                    return None

                mock_to_thread.side_effect = fake_to_thread

                # --- Run 1 ---
                summary1 = await run_ingestion_job(session)
                assert summary1.staged_count == 1
                assert summary1.skipped_count == 0
                assert summary1.failed_count == 0

                # Verify DB state after run 1
                rows = (await session.execute(select(StagedAttachment))).scalars().all()
                assert len(rows) == 1
                assert rows[0].gmail_part_id == "1"
                assert rows[0].gmail_attachment_id == "att-A1"

                # --- Run 2 (attachment_id rotated) ---
                run_state["run"] = 2
                summary2 = await run_ingestion_job(session)
                assert summary2.staged_count == 0, (
                    "Run 2 should NOT stage new rows when part_id is stable"
                )
                assert summary2.skipped_count == 1
                assert summary2.failed_count == 0

                rows = (await session.execute(select(StagedAttachment))).scalars().all()
                assert len(rows) == 1, (
                    "DB should still have exactly 1 row after two runs"
                )

        await engine.dispose()

    @patch("ccas.ingestor.job.asyncio.to_thread")
    @patch("ccas.ingestor.job.build_gmail_service")
    @patch("ccas.ingestor.job.load_credentials")
    @patch("ccas.ingestor.job.get_settings")
    async def test_legacy_row_matched_by_filename_and_backfilled(
        self,
        mock_get_settings,
        mock_load_creds,
        mock_build_service,
        mock_to_thread,
    ):
        """舊資料 (gmail_part_id IS NULL) 透過 filename fallback 命中並 backfill。"""
        engine, factory = await _create_test_session()
        with tempfile.TemporaryDirectory() as tmp:
            staging_path = Path(tmp) / "CTBC" / "msg-STABLE_bill.pdf"
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            staging_path.write_bytes(b"legacy-content")

            async with factory() as session:
                session.add(
                    BankConfig(
                        bank_code="CTBC",
                        bank_name="CTBC",
                        gmail_filter="from:ctbc@example.com",
                        is_active=True,
                    )
                )
                # Pre-insert legacy row with NULL part_id
                legacy = StagedAttachment(
                    bank_code="CTBC",
                    gmail_message_id="msg-STABLE",
                    gmail_attachment_id="att-LEGACY",
                    gmail_part_id=None,
                    message_date=datetime(2026, 3, 10),
                    original_filename="bill.pdf",
                    staged_path=str(staging_path),
                    status="staged",
                )
                session.add(legacy)
                await session.commit()

                mock_get_settings.return_value = _mock_settings(tmp)
                mock_load_creds.return_value = MagicMock()
                mock_build_service.return_value = MagicMock()

                call_state = {"n": 0}

                async def fake_to_thread(fn, *args, **kwargs):
                    call_state["n"] += 1
                    if call_state["n"] == 1:
                        return [_message_with("att-NEW")]
                    if call_state["n"] == 2:
                        return b"fake-pdf-bytes"
                    return None

                mock_to_thread.side_effect = fake_to_thread

                summary = await run_ingestion_job(session)
                assert summary.staged_count == 0, (
                    "Legacy row should match via filename fallback"
                )
                assert summary.skipped_count == 1

                rows = (await session.execute(select(StagedAttachment))).scalars().all()
                assert len(rows) == 1
                # Backfill should have written part_id into the legacy row
                assert rows[0].gmail_part_id == "1"
                assert rows[0].gmail_attachment_id == "att-LEGACY"

        await engine.dispose()
