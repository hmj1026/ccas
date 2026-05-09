"""Force 模式下 fetch_parseable_attachments 擴大查詢範圍的測試。"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.parser.staging import fetch_parseable_attachments
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import Base, StagedAttachment


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


def _make_attachment(
    status: str,
    message_id: str = "msg-001",
    attachment_id: str = "att-001",
) -> StagedAttachment:
    return StagedAttachment(
        bank_code="CTBC",
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=datetime(2026, 3, 10),
        original_filename="bill.pdf",
        staged_path="/data/staging/CTBC/bill.pdf",
        status=status,
    )


class TestForceFetch:
    async def test_normal_mode_returns_decrypted_only(self, db_session):
        db_session.add(_make_attachment("decrypted", attachment_id="a1"))
        db_session.add(_make_attachment("parsed", message_id="m2", attachment_id="a2"))
        db_session.add(
            _make_attachment("parse_failed", message_id="m3", attachment_id="a3")
        )
        await db_session.flush()

        results = await fetch_parseable_attachments(db_session)
        assert len(results) == 1
        assert results[0].status == "decrypted"

    async def test_force_mode_includes_parsed_and_failed(self, db_session):
        db_session.add(_make_attachment("decrypted", attachment_id="a1"))
        db_session.add(_make_attachment("parsed", message_id="m2", attachment_id="a2"))
        db_session.add(
            _make_attachment("parse_failed", message_id="m3", attachment_id="a3")
        )
        db_session.add(
            _make_attachment("parse_skipped", message_id="m4", attachment_id="a4")
        )
        await db_session.flush()

        options = PipelineOptions(force=True)
        results = await fetch_parseable_attachments(db_session, options)
        statuses = {r.status for r in results}
        assert statuses == {"decrypted", "parsed", "parse_failed", "parse_skipped"}
        assert len(results) == 4

    async def test_force_mode_excludes_staged(self, db_session):
        db_session.add(_make_attachment("staged", attachment_id="a1"))
        await db_session.flush()

        options = PipelineOptions(force=True)
        results = await fetch_parseable_attachments(db_session, options)
        assert len(results) == 0

    async def test_force_false_explicit(self, db_session):
        db_session.add(_make_attachment("parsed", attachment_id="a1"))
        await db_session.flush()

        options = PipelineOptions(force=False)
        results = await fetch_parseable_attachments(db_session, options)
        assert len(results) == 0
