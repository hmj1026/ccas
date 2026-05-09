"""Tests for ccas.tools.cleanup_gmail_state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import Base, GmailOAuthState
from ccas.tools.cleanup_gmail_state import cleanup_expired_state


@pytest.fixture
async def in_memory_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestCleanupExpiredState:
    async def test_removes_only_rows_older_than_max_age(
        self, in_memory_session: AsyncSession
    ) -> None:
        now = datetime.now(UTC)
        in_memory_session.add_all(
            [
                GmailOAuthState(state="recent", code_verifier="v1", created_at=now),
                GmailOAuthState(
                    state="day-old",
                    code_verifier="v2",
                    created_at=now - timedelta(hours=23, minutes=59),
                ),
                GmailOAuthState(
                    state="ancient",
                    code_verifier="v3",
                    created_at=now - timedelta(days=2),
                ),
            ]
        )
        await in_memory_session.commit()

        removed = await cleanup_expired_state(
            in_memory_session, max_age=timedelta(hours=24)
        )
        await in_memory_session.commit()

        assert removed == 1
        rows = (
            (await in_memory_session.execute(select(GmailOAuthState))).scalars().all()
        )
        states = {r.state for r in rows}
        assert states == {"recent", "day-old"}

    async def test_returns_zero_when_no_expired_rows(
        self, in_memory_session: AsyncSession
    ) -> None:
        in_memory_session.add(
            GmailOAuthState(
                state="fresh",
                code_verifier="v",
                created_at=datetime.now(UTC),
            )
        )
        await in_memory_session.commit()

        removed = await cleanup_expired_state(in_memory_session)
        await in_memory_session.commit()

        assert removed == 0
