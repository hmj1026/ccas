"""run_decryption_job 與 _process_attachment 的協調與錯誤路徑單元測試。

聚焦 ccas.decryptor.job 中尚未被既有測試覆蓋的部分：
單筆附件解密的各分支（缺 staged_path / 路徑逃逸 / 解密失敗 / 解密異常 /
解密成功 / 透通），以及批次層的密碼快取失敗略過、per-item rollback、
進度回報失敗時的容錯。實際 DB 動作走 in-memory SQLite，其餘相依以
patch 取代。
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.decryptor.decrypt import DecryptionError, DecryptResult
from ccas.decryptor.job import (
    DecryptionSummary,
    _process_attachment,
    run_decryption_job,
)
from ccas.errors import DecryptError
from ccas.shared.progress import ProgressReporter
from ccas.storage.models import Base, StagedAttachment, StagedAttachmentStatus

# patch 目標：以 job 模組中匯入的名稱為準。
GET_SETTINGS = "ccas.decryptor.job.get_settings"
RESOLVE_STAGED = "ccas.decryptor.job.resolve_staged_path"
DECRYPT_MULTI = "ccas.decryptor.job.decrypt_pdf_multi"
RESOLVE_PASSWORDS = "ccas.decryptor.job.resolve_passwords"
UPDATE_STATUS = "ccas.decryptor.job.update_attachment_status"
FETCH_PENDING = "ccas.decryptor.job.fetch_pending_attachments"


@pytest.fixture
async def db_session():
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


def _settings() -> SimpleNamespace:
    return SimpleNamespace(staging_dir="/tmp/staging")


def _make_attachment(
    *,
    status: str = StagedAttachmentStatus.STAGED,
    staged_path: str | None = "/tmp/staging/CTBC/bill.pdf",
    bank_code: str = "CTBC",
    message_id: str = "msg-001",
    attachment_id: str = "att-001",
) -> StagedAttachment:
    return StagedAttachment(
        bank_code=bank_code,
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=datetime(2026, 3, 10),
        original_filename="bill.pdf",
        staged_path=staged_path,
        status=status,
    )


async def _add(session: AsyncSession, attachment: StagedAttachment) -> StagedAttachment:
    session.add(attachment)
    await session.flush()
    return attachment


class _RaisingItemReporter(ProgressReporter):
    """stage_item_done 會拋例外的 reporter，用以觸發 finally 容錯分支。"""

    def __init__(self) -> None:
        self.started = 0
        self.item_done_attempts = 0

    async def stage_started(self, stage: str, total: int) -> None:
        self.started += 1

    async def stage_item_done(self, stage: str, processed: int) -> None:
        self.item_done_attempts += 1
        raise RuntimeError("reporter boom")

    async def stage_finished(
        self,
        stage: str,
        ok: int,
        fail: int,
        elapsed_ms: int,
        *,
        counts=None,
        errors=None,
    ) -> None:
        return None


class TestProcessAttachment:
    """單筆附件 _process_attachment 的所有分支。"""

    async def test_missing_staged_path_marks_failed(self, db_session):
        att = await _add(db_session, _make_attachment(staged_path=None))
        summary = DecryptionSummary()

        with patch(GET_SETTINGS, return_value=_settings()):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.failed_count == 1
        assert len(summary.errors) == 1
        assert "缺少 staged_path" in summary.errors[0]
        assert att.status == StagedAttachmentStatus.DECRYPT_FAILED
        assert att.error_reason is not None

    async def test_path_escape_marks_failed(self, db_session):
        att = await _add(db_session, _make_attachment())
        summary = DecryptionSummary()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(RESOLVE_STAGED, side_effect=ValueError("escape")),
        ):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.failed_count == 1
        assert "逃逸" in summary.errors[0]
        assert att.status == StagedAttachmentStatus.DECRYPT_FAILED

    async def test_decryption_error_marks_failed(self, db_session):
        att = await _add(db_session, _make_attachment())
        summary = DecryptionSummary()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, side_effect=DecryptionError("Invalid password")),
        ):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.failed_count == 1
        assert "解密失敗" in summary.errors[0]
        assert att.status == StagedAttachmentStatus.DECRYPT_FAILED
        assert att.error_reason is not None

    async def test_unexpected_exception_marks_failed(self, db_session):
        att = await _add(db_session, _make_attachment())
        summary = DecryptionSummary()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, side_effect=RuntimeError("boom")),
        ):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.failed_count == 1
        assert "解密異常" in summary.errors[0]
        assert att.status == StagedAttachmentStatus.DECRYPT_FAILED

    async def test_decrypted_success_increments_decrypted(self, db_session):
        att = await _add(db_session, _make_attachment())
        summary = DecryptionSummary()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, return_value=DecryptResult(needed_decryption=True)),
        ):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.decrypted_count == 1
        assert summary.passthrough_count == 0
        assert summary.failed_count == 0
        assert att.status == StagedAttachmentStatus.DECRYPTED
        assert att.error_reason is None

    async def test_passthrough_increments_passthrough(self, db_session):
        att = await _add(db_session, _make_attachment())
        summary = DecryptionSummary()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, return_value=DecryptResult(needed_decryption=False)),
        ):
            await _process_attachment(att, db_session, summary, ("pw1",))

        assert summary.passthrough_count == 1
        assert summary.decrypted_count == 0
        assert att.status == StagedAttachmentStatus.DECRYPTED


class TestRunDecryptionJob:
    """批次協調 run_decryption_job。"""

    async def test_no_attachments_returns_empty_summary(self, db_session):
        summary = await run_decryption_job(db_session)

        assert isinstance(summary, DecryptionSummary)
        assert summary.decrypted_count == 0
        assert summary.passthrough_count == 0
        assert summary.failed_count == 0
        assert summary.errors == []

    async def test_password_resolution_failure_skips_bank(self, db_session):
        att = await _add(db_session, _make_attachment())

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(
                RESOLVE_PASSWORDS,
                new_callable=AsyncMock,
                side_effect=DecryptError("PDF 密碼解密失敗", "master.key 不匹配"),
            ),
        ):
            summary = await run_decryption_job(db_session)

        assert summary.failed_count == 1
        assert summary.decrypted_count == 0
        assert "密碼解析失敗" in summary.errors[0]
        assert att.status == StagedAttachmentStatus.DECRYPT_FAILED

    async def test_happy_path_decrypts_and_commits(self, db_session):
        att = await _add(db_session, _make_attachment())

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(
                RESOLVE_PASSWORDS,
                new_callable=AsyncMock,
                return_value=("pw1",),
            ),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, return_value=DecryptResult(needed_decryption=True)),
        ):
            summary = await run_decryption_job(db_session)

        assert summary.decrypted_count == 1
        assert summary.failed_count == 0
        assert att.status == StagedAttachmentStatus.DECRYPTED

    async def test_item_exception_rolls_back_and_continues(self):
        # 用 fake session：真實 AsyncSession 在 rollback 後會 expire 屬性，
        # 後續 logger.exception 存取 attachment.bank_code 會觸發 sync lazy-load
        # （MissingGreenlet）。fake session 讓 transient 物件屬性保持可讀，
        # 聚焦驗證「per-item except → rollback → 批次續行」的分支邏輯。
        att = _make_attachment()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(FETCH_PENDING, new_callable=AsyncMock, return_value=[att]),
            patch(
                RESOLVE_PASSWORDS,
                new_callable=AsyncMock,
                return_value=("pw1",),
            ),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, return_value=DecryptResult(needed_decryption=True)),
            patch(
                UPDATE_STATUS,
                new_callable=AsyncMock,
                side_effect=RuntimeError("db write boom"),
            ) as mock_update,
        ):
            # 不應對外拋出：例外被 per-item except 捕捉並 rollback 後續行。
            summary = await run_decryption_job(session)

        assert isinstance(summary, DecryptionSummary)
        assert mock_update.await_count == 1
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        # decrypted_count 在 update 失敗前已自增，rollback 不影響記憶體計數。
        assert summary.decrypted_count == 1

    async def test_reporter_failure_does_not_abort_batch(self, db_session):
        att = await _add(db_session, _make_attachment())
        reporter = _RaisingItemReporter()

        with (
            patch(GET_SETTINGS, return_value=_settings()),
            patch(
                RESOLVE_PASSWORDS,
                new_callable=AsyncMock,
                return_value=("pw1",),
            ),
            patch(RESOLVE_STAGED, return_value=Path("/tmp/staging/CTBC/bill.pdf")),
            patch(DECRYPT_MULTI, return_value=DecryptResult(needed_decryption=True)),
        ):
            summary = await run_decryption_job(db_session, reporter=reporter)

        assert summary.decrypted_count == 1
        assert reporter.item_done_attempts == 1
        assert att.status == StagedAttachmentStatus.DECRYPTED
