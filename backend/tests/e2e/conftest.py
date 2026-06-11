"""E2E 測試共用 Fixtures。

提供 in-memory SQLite DB Session 與測試用資料工廠函式。
外部服務（Gmail、Telegram）由各測試自行 mock。
"""

import os
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage.models import BankConfig, Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test-token")


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供 in-memory SQLite 的 AsyncSession，測試後清除所有資料表。"""
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


@pytest.fixture
async def bank_config(db_session: AsyncSession) -> BankConfig:
    """建立測試用銀行設定。"""
    config = BankConfig(
        bank_code="TESTBANK",
        bank_name="測試銀行",
        gmail_filter="from:testbank@example.com",
        pdf_password_rule="static",
        active_parser_version="v1",
        is_active=True,
    )
    db_session.add(config)
    await db_session.commit()
    return config


@pytest.fixture
def staging_dir(tmp_path: Path) -> str:
    """Provide a temporary staging directory for pipeline tests."""
    staging = tmp_path / "staging"
    staging.mkdir()
    return str(staging)


@pytest.fixture
async def staged_attachment(
    db_session: AsyncSession, bank_config: BankConfig
) -> StagedAttachment:
    """建立一筆狀態為 staged 的附件記錄。"""
    attachment = StagedAttachment(
        bank_code=bank_config.bank_code,
        gmail_message_id="msg-001",
        gmail_attachment_id="att-001",
        message_date=datetime(2026, 3, 1),
        original_filename="statement.pdf",
        staged_path="/tmp/test-staging/TESTBANK/msg-001/statement.pdf",
        status="staged",
    )
    db_session.add(attachment)
    await db_session.commit()
    return attachment


@pytest.fixture
async def decrypted_attachment(
    db_session: AsyncSession, bank_config: BankConfig
) -> StagedAttachment:
    """建立一筆狀態為 decrypted 的附件記錄。"""
    attachment = StagedAttachment(
        bank_code=bank_config.bank_code,
        gmail_message_id="msg-002",
        gmail_attachment_id="att-002",
        message_date=datetime(2026, 3, 1),
        original_filename="statement.pdf",
        staged_path="/tmp/test-staging/TESTBANK/msg-002/statement.pdf",
        status="decrypted",
    )
    db_session.add(attachment)
    await db_session.commit()
    return attachment
