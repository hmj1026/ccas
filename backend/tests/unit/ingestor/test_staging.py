"""PDF 附件 staging path、dedupe 與記錄建立的單元測試。"""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.staging import (
    backfill_part_id,
    build_staged_path,
    create_staged_record,
    find_existing_staged,
)
from ccas.storage.models import Base, StagedAttachment, StagedAttachmentStatus


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


class TestBuildStagedPath:
    """build_staged_path() 的測試案例。"""

    def test_path_structure(self):
        """驗證路徑格式為 {staging_dir}/{bank_code}/{message_id[:12]}_{filename}。"""
        result = build_staged_path(
            "/data/staging", "CTBC", "abc123def456xyz", "bill.pdf"
        )
        assert result == Path("/data/staging/CTBC/abc123def456_bill.pdf")

    def test_different_banks_isolated(self):
        """不同銀行使用不同子目錄。"""
        ctbc = build_staged_path("/data/staging", "CTBC", "msg001", "a.pdf")
        cathay = build_staged_path("/data/staging", "CATHAY", "msg001", "a.pdf")
        assert ctbc.parent != cathay.parent
        assert ctbc.parent.name == "CTBC"
        assert cathay.parent.name == "CATHAY"

    def test_short_message_id(self):
        """message_id 短於 12 字元時不會出錯。"""
        result = build_staged_path("/data/staging", "CTBC", "abc", "bill.pdf")
        assert result == Path("/data/staging/CTBC/abc_bill.pdf")

    def test_strips_attachment_path_segments(self):
        """附件檔名含路徑片段時只保留 basename。"""
        result = build_staged_path(
            "/data/staging", "CTBC", "abc123def456xyz", "../../evil.pdf"
        )
        assert result == Path("/data/staging/CTBC/abc123def456_evil.pdf")

    def test_rejects_empty_attachment_filename(self):
        """空白或無效檔名應直接拒絕。"""
        with pytest.raises(ValueError, match="filename"):
            build_staged_path("/data/staging", "CTBC", "abc123", "../")

    def test_rejects_invalid_bank_code(self):
        """bank_code 不能包含路徑控制字元。"""
        with pytest.raises(ValueError, match="bank_code"):
            build_staged_path("/data/staging", "../CTBC", "abc123", "bill.pdf")


class TestFindExistingStaged:
    """find_existing_staged() 的測試案例（使用 stable part_id dedupe 鍵）。"""

    async def test_returns_none_when_not_found(self, db_session):
        """DB 為空時回傳 None。"""
        result = await find_existing_staged(
            db_session, "msg-999", part_id="1", original_filename="bill.pdf"
        )
        assert result is None

    async def test_primary_query_matches_part_id(self, db_session):
        """主查詢：以 (message_id, part_id) 命中既有記錄。"""
        record = StagedAttachment(
            bank_code="CTBC",
            gmail_message_id="msg-001",
            gmail_attachment_id="att-ROTATED-A",
            gmail_part_id="1",
            message_date=datetime(2026, 3, 10),
            original_filename="bill.pdf",
            staged_path="/data/staging/CTBC/msg-001_bill.pdf",
            status="staged",
        )
        db_session.add(record)
        await db_session.flush()

        # 即使 attachment_id 不同（模擬 Gmail API 重生 token），
        # 只要 part_id 相同仍命中。
        result = await find_existing_staged(
            db_session, "msg-001", part_id="1", original_filename="bill.pdf"
        )
        assert result is not None
        assert result.gmail_part_id == "1"

    async def test_fallback_matches_by_filename_when_part_id_null(self, db_session):
        """Fallback：part_id 為 NULL 的舊資料以 filename 比對命中。"""
        legacy = StagedAttachment(
            bank_code="CTBC",
            gmail_message_id="msg-legacy",
            gmail_attachment_id="att-LEGACY",
            gmail_part_id=None,
            message_date=datetime(2026, 3, 10),
            original_filename="legacy.pdf",
            staged_path="/data/staging/CTBC/msg-legacy_legacy.pdf",
            status="staged",
        )
        db_session.add(legacy)
        await db_session.flush()

        result = await find_existing_staged(
            db_session, "msg-legacy", part_id="1", original_filename="legacy.pdf"
        )
        assert result is not None
        assert result.gmail_attachment_id == "att-LEGACY"
        assert result.gmail_part_id is None  # 尚未 backfill

    async def test_primary_takes_precedence_over_fallback(self, db_session):
        """同 message_id 下若有 part_id 命中的列，絕不走 fallback。"""
        db_session.add_all(
            [
                StagedAttachment(
                    bank_code="CTBC",
                    gmail_message_id="msg-mixed",
                    gmail_attachment_id="att-LEGACY",
                    gmail_part_id=None,
                    message_date=datetime(2026, 3, 10),
                    original_filename="bill.pdf",
                    staged_path="/legacy/bill.pdf",
                    status="staged",
                ),
                StagedAttachment(
                    bank_code="CTBC",
                    gmail_message_id="msg-mixed",
                    gmail_attachment_id="att-NEW",
                    gmail_part_id="1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="bill.pdf",
                    staged_path="/new/bill.pdf",
                    status="staged",
                ),
            ]
        )
        await db_session.flush()

        result = await find_existing_staged(
            db_session, "msg-mixed", part_id="1", original_filename="bill.pdf"
        )
        assert result is not None
        assert result.gmail_attachment_id == "att-NEW"
        assert result.gmail_part_id == "1"

    async def test_no_match_when_filename_differs_and_no_part_id(self, db_session):
        """Fallback 僅在 filename 相符時命中，否則回傳 None。"""
        db_session.add(
            StagedAttachment(
                bank_code="CTBC",
                gmail_message_id="msg-other",
                gmail_attachment_id="att-X",
                gmail_part_id=None,
                message_date=datetime(2026, 3, 10),
                original_filename="other.pdf",
                staged_path="/data/staging/CTBC/other.pdf",
                status="staged",
            )
        )
        await db_session.flush()

        result = await find_existing_staged(
            db_session, "msg-other", part_id="1", original_filename="bill.pdf"
        )
        assert result is None


class TestBackfillPartId:
    """backfill_part_id() 的測試案例。"""

    async def test_backfills_null_part_id(self, db_session):
        """對 gmail_part_id 為 NULL 的舊紀錄寫入 part_id。"""
        record = StagedAttachment(
            bank_code="CTBC",
            gmail_message_id="msg-001",
            gmail_attachment_id="att-001",
            gmail_part_id=None,
            message_date=datetime(2026, 3, 10),
            original_filename="bill.pdf",
            staged_path="/data/staging/CTBC/bill.pdf",
            status="staged",
        )
        db_session.add(record)
        await db_session.flush()

        await backfill_part_id(db_session, record, part_id="1")
        assert record.gmail_part_id == "1"

    async def test_no_op_when_part_id_already_set(self, db_session):
        """已存在 part_id 的紀錄不會被覆蓋。"""
        record = StagedAttachment(
            bank_code="CTBC",
            gmail_message_id="msg-002",
            gmail_attachment_id="att-002",
            gmail_part_id="0.1",
            message_date=datetime(2026, 3, 10),
            original_filename="bill.pdf",
            staged_path="/data/staging/CTBC/bill.pdf",
            status="staged",
        )
        db_session.add(record)
        await db_session.flush()

        await backfill_part_id(db_session, record, part_id="different")
        assert record.gmail_part_id == "0.1"

    async def test_no_op_when_part_id_empty(self, db_session):
        """空字串 part_id 不寫入。"""
        record = StagedAttachment(
            bank_code="CTBC",
            gmail_message_id="msg-003",
            gmail_attachment_id="att-003",
            gmail_part_id=None,
            message_date=datetime(2026, 3, 10),
            original_filename="bill.pdf",
            staged_path="/data/staging/CTBC/bill.pdf",
            status="staged",
        )
        db_session.add(record)
        await db_session.flush()

        await backfill_part_id(db_session, record, part_id="")
        assert record.gmail_part_id is None


class TestCreateStagedRecord:
    """create_staged_record() 的測試案例。"""

    async def test_persists_staged_record(self, db_session):
        """成功建立並持久化 staging 記錄。"""
        record = await create_staged_record(
            db_session,
            bank_code="CTBC",
            message_id="msg-001",
            attachment_id="att-001",
            message_date=datetime(2026, 3, 10),
            original_filename="bill.pdf",
            staged_path="/data/staging/CTBC/msg-001_bill.pdf",
            status=StagedAttachmentStatus.STAGED,
        )

        assert record.id is not None

        stmt = select(StagedAttachment).where(StagedAttachment.id == record.id)
        result = await db_session.execute(stmt)
        persisted = result.scalar_one()

        assert persisted.bank_code == "CTBC"
        assert persisted.status == "staged"
        assert persisted.error_reason is None

    async def test_persists_failed_record_with_error(self, db_session):
        """失敗記錄包含 error_reason。"""
        record = await create_staged_record(
            db_session,
            bank_code="CATHAY",
            message_id="msg-002",
            attachment_id="att-002",
            message_date=datetime(2026, 3, 15),
            original_filename="statement.pdf",
            staged_path=None,
            status=StagedAttachmentStatus.FAILED,
            error_reason="HttpError 500: Internal Server Error",
        )

        assert record.status == "failed"
        assert record.error_reason == "HttpError 500: Internal Server Error"
        assert record.staged_path is None
