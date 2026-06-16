"""ccas.storage.queries.fetch_bank_names 的單元測試。

cache 已移除（P3：跨 process 各持陳舊副本，Setup UI 改名最久 5 分鐘才生效），
``fetch_bank_names`` 每次都重新查詢；測試聚焦於 fresh-read 語意。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage.models import BankConfig, Base
from ccas.storage.queries import fetch_bank_names
from ccas.tools.bank_configs import BankConfigSpec, sync_bank_configs


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_bank(session: AsyncSession, code: str, name: str) -> None:
    session.add(BankConfig(bank_code=code, bank_name=name, gmail_filter=f"from:{code}"))
    await session.commit()


class TestFetchBankNames:
    async def test_returns_bank_code_to_name_mapping(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

    async def test_reflects_new_rows_immediately(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

        # 無快取：新增的 bank 立刻可見，不需等待 TTL 或手動 invalidate。
        await _seed_bank(session, "ESUN", "玉山銀行")
        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }

    async def test_returned_dict_is_independent(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        first = await fetch_bank_names(session)
        first["HACK"] = "mutated"

        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}


class TestSyncBankConfigsVisibility:
    async def test_apply_sync_is_visible_immediately(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        await fetch_bank_names(session)

        specs = [
            BankConfigSpec(
                bank_code="ESUN",
                bank_name="玉山銀行",
                gmail_filter="from:esun",
            )
        ]
        await sync_bank_configs(session, specs, apply_changes=True)

        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }
