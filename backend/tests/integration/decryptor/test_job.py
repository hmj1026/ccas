"""批次解密 job 的整合測試：多附件混合情境與 batch summary。"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.decryptor.decrypt import DecryptionError, DecryptResult
from ccas.decryptor.job import run_decryption_job
from ccas.storage.models import Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")
os.environ.setdefault("API_TOKEN", "test")


async def _create_test_session():
    """建立 in-memory DB + session。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


def _make_attachment(
    bank_code: str,
    message_id: str,
    attachment_id: str,
    status: str = "staged",
    staged_path: str = "/data/staging/test/bill.pdf",
) -> StagedAttachment:
    return StagedAttachment(
        bank_code=bank_code,
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=datetime(2026, 3, 10),
        original_filename=f"{attachment_id}.pdf",
        staged_path=staged_path,
        status=status,
    )


class TestMixedBatchScenario:
    """多附件混合情境（成功解密、透通、失敗）的測試案例。"""

    @patch("ccas.decryptor.job.asyncio.to_thread")
    @patch("ccas.decryptor.job.get_settings")
    async def test_mixed_batch_summary(self, mock_get_settings, mock_to_thread):
        """驗證 batch summary 正確統計成功、透通與失敗。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            # Attachment 1: encrypted, will succeed
            session.add(
                _make_attachment("CTBC", "msg-1", "att-1", staged_path="/tmp/1.pdf")
            )
            # Attachment 2: unencrypted, will passthrough
            session.add(
                _make_attachment("CATHAY", "msg-2", "att-2", staged_path="/tmp/2.pdf")
            )
            # Attachment 3: encrypted, wrong password, will fail
            session.add(
                _make_attachment("ESUN", "msg-3", "att-3", staged_path="/tmp/3.pdf")
            )
            # Attachment 4: already decrypted, should be skipped (not fetched)
            session.add(
                _make_attachment(
                    "CTBC", "msg-4", "att-4", status="decrypted",
                    staged_path="/tmp/4.pdf",
                )
            )
            await session.commit()

            mock_settings = MagicMock()
            mock_settings.get_pdf_password.side_effect = lambda code: {
                "CTBC": "correct_pw",
                "CATHAY": None,
                "ESUN": "wrong_pw",
            }.get(code.upper())
            mock_get_settings.return_value = mock_settings

            async def fake_to_thread(fn, *args):
                pdf_path = args[0]
                if str(pdf_path) == "/tmp/1.pdf":
                    return DecryptResult(needed_decryption=True)
                if str(pdf_path) == "/tmp/2.pdf":
                    return DecryptResult(needed_decryption=False)
                if str(pdf_path) == "/tmp/3.pdf":
                    raise DecryptionError("Invalid password")
                raise AssertionError(f"Unexpected call: {pdf_path}")

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_decryption_job(session)

            assert summary.decrypted_count == 1
            assert summary.passthrough_count == 1
            assert summary.failed_count == 1
            assert summary.skipped_count == 0
            assert len(summary.errors) == 1
            assert "Invalid password" in summary.errors[0]

        await engine.dispose()

    @patch("ccas.decryptor.job.asyncio.to_thread")
    @patch("ccas.decryptor.job.get_settings")
    async def test_failed_attachment_status_persisted(
        self, mock_get_settings, mock_to_thread
    ):
        """解密失敗的附件狀態與 error_reason 被正確持久化。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                _make_attachment(
                    "ESUN", "msg-fail", "att-fail",
                    staged_path="/tmp/f.pdf",
                )
            )
            await session.commit()

            mock_settings = MagicMock()
            mock_settings.get_pdf_password.return_value = "bad_pw"
            mock_get_settings.return_value = mock_settings

            async def fake_to_thread(fn, *args):
                raise DecryptionError("Invalid password")

            mock_to_thread.side_effect = fake_to_thread

            await run_decryption_job(session)

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-fail"
            )
            result = await session.execute(stmt)
            record = result.scalar_one()
            assert record.status == "decrypt_failed"
            assert record.error_reason is not None
            assert "Invalid password" in record.error_reason

        await engine.dispose()

    @patch("ccas.decryptor.job.asyncio.to_thread")
    @patch("ccas.decryptor.job.get_settings")
    async def test_single_failure_does_not_abort_batch(
        self, mock_get_settings, mock_to_thread
    ):
        """單筆失敗不中止整批，後續附件仍被處理。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                _make_attachment("FAIL", "msg-1", "att-1", staged_path="/tmp/a.pdf")
            )
            session.add(
                _make_attachment("OK", "msg-2", "att-2", staged_path="/tmp/b.pdf")
            )
            await session.commit()

            mock_settings = MagicMock()
            mock_settings.get_pdf_password.return_value = None
            mock_get_settings.return_value = mock_settings

            call_paths = []

            async def fake_to_thread(fn, *args):
                pdf_path = args[0]
                call_paths.append(str(pdf_path))
                if str(pdf_path) == "/tmp/a.pdf":
                    raise DecryptionError("Password not found in settings")
                return DecryptResult(needed_decryption=False)

            mock_to_thread.side_effect = fake_to_thread

            summary = await run_decryption_job(session)

            assert len(call_paths) == 2
            assert summary.failed_count == 1
            assert summary.passthrough_count == 1

        await engine.dispose()

    @patch("ccas.decryptor.job.asyncio.to_thread")
    @patch("ccas.decryptor.job.get_settings")
    async def test_empty_batch_returns_zero_summary(
        self, mock_get_settings, mock_to_thread
    ):
        """沒有待解密附件時回傳全零 summary。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            summary = await run_decryption_job(session)

            assert summary.decrypted_count == 0
            assert summary.passthrough_count == 0
            assert summary.failed_count == 0
            assert summary.skipped_count == 0
            mock_to_thread.assert_not_called()

        await engine.dispose()
