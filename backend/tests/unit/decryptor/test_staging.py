"""解密 staging 資料存取層的單元測試。"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.decryptor.staging import fetch_pending_attachments, update_attachment_status
from ccas.storage.models import Base, StagedAttachment


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


def _make_attachment(
    bank_code: str = "CTBC",
    message_id: str = "msg-001",
    attachment_id: str = "att-001",
    status: str = "staged",
    staged_path: str = "/data/staging/CTBC/bill.pdf",
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


class TestFetchPendingAttachments:
    """fetch_pending_attachments() 的測試案例。"""

    async def test_returns_staged_only(self, db_session):
        """只回傳 status='staged' 的附件。"""
        db_session.add(_make_attachment(status="staged", attachment_id="att-1"))
        db_session.add(
            _make_attachment(
                status="decrypted",
                message_id="msg-2",
                attachment_id="att-2",
            )
        )
        db_session.add(
            _make_attachment(status="failed", message_id="msg-3", attachment_id="att-3")
        )
        await db_session.flush()

        results = await fetch_pending_attachments(db_session)
        assert len(results) == 1
        assert results[0].status == "staged"

    async def test_returns_empty_when_none_staged(self, db_session):
        """沒有 staged 附件時回傳空清單。"""
        db_session.add(_make_attachment(status="decrypted", attachment_id="att-1"))
        await db_session.flush()

        results = await fetch_pending_attachments(db_session)
        assert len(results) == 0

    async def test_idempotent_decrypted_not_refetched(self, db_session):
        """已為 decrypted 的附件不會被重新取出（idempotent 保護）。"""
        att = _make_attachment(status="decrypted", attachment_id="att-1")
        db_session.add(att)
        await db_session.flush()

        results = await fetch_pending_attachments(db_session)
        assert len(results) == 0


class TestUpdateAttachmentStatus:
    """update_attachment_status() 的測試案例。"""

    async def test_update_to_decrypted(self, db_session):
        """成功更新狀態為 decrypted。"""
        att = _make_attachment()
        db_session.add(att)
        await db_session.flush()

        await update_attachment_status(db_session, att, status="decrypted")
        assert att.status == "decrypted"
        assert att.error_reason is None

    async def test_update_to_decrypt_failed_with_reason(self, db_session):
        """更新為 decrypt_failed 並寫入 error_reason。"""
        att = _make_attachment()
        db_session.add(att)
        await db_session.flush()

        await update_attachment_status(
            db_session,
            att,
            status="decrypt_failed",
            error_reason="Invalid password",
        )
        assert att.status == "decrypt_failed"
        assert att.error_reason == "Invalid password"
