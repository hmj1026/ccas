"""Tests for ccas.tools.cleanup_gmail_state."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ccas.tools.cleanup_gmail_state as cleanup_mod
from ccas.storage.models import Base, GmailOAuthState
from ccas.tools.cleanup_gmail_state import cleanup_expired_state, main


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


async def _setup_file_db(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                GmailOAuthState(
                    state="old",
                    code_verifier="v1",
                    created_at=now - timedelta(days=5),
                ),
                GmailOAuthState(state="new", code_verifier="v2", created_at=now),
            ]
        )
        await session.commit()
    await engine.dispose()


async def _surviving_states(url: str) -> set[str]:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        rows = (await session.execute(select(GmailOAuthState))).scalars().all()
    await engine.dispose()
    return {r.state for r in rows}


class TestCli:
    def test_main_with_database_url_owns_and_disposes_engine(
        self, tmp_path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "cleanup.db"
        url = f"sqlite+aiosqlite:///{db_path}"
        asyncio.run(_setup_file_db(url))

        rc = main(["--database-url", url, "--max-age-hours", "1"])

        assert rc == 0
        assert "removed=1" in capsys.readouterr().out
        assert asyncio.run(_surviving_states(url)) == {"new"}

    async def test_run_cli_default_branch_uses_module_singletons(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            session.add(
                GmailOAuthState(
                    state="stale",
                    code_verifier="v",
                    created_at=datetime.now(UTC) - timedelta(days=3),
                )
            )
            await session.commit()

        monkeypatch.setattr(cleanup_mod, "get_engine", lambda: engine)
        monkeypatch.setattr(cleanup_mod, "get_session_factory", lambda: factory)

        rc = await cleanup_mod._run_cli(None, 1)

        assert rc == 0
        assert "removed=1" in capsys.readouterr().out
        # owns_engine is False here: engine NOT disposed, still usable.
        async with factory() as session:
            remaining = (await session.execute(select(GmailOAuthState))).scalars().all()
        assert remaining == []
        await engine.dispose()
