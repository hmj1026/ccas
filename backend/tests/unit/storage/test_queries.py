"""ccas.storage.queries 銀行名稱 TTL 快取的單元測試。"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Generator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage import queries
from ccas.storage.models import BankConfig, Base
from ccas.storage.queries import fetch_bank_names, invalidate_bank_names_cache
from ccas.tools.bank_configs import BankConfigSpec, sync_bank_configs


@pytest.fixture(autouse=True)
def _fresh_cache() -> Generator[None, None, None]:
    """Reset the module-level cache so tests never see leaked entries."""
    invalidate_bank_names_cache()
    yield
    invalidate_bank_names_cache()


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


def _expire_cache_entry() -> None:
    """Rewind the cached entry's expiry so the TTL appears lapsed.

    Patching ``time.monotonic`` globally would disturb the asyncio event
    loop, so the test mutates the cache entry directly instead.
    """
    _, mapping = queries._bank_names_cache[queries._BANK_NAMES_CACHE_KEY]
    queries._bank_names_cache[queries._BANK_NAMES_CACHE_KEY] = (
        time.monotonic() - 1,
        mapping,
    )


class TestFetchBankNamesCache:
    async def test_returns_bank_code_to_name_mapping(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

    async def test_second_call_within_ttl_returns_cached_result(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

        # New row is invisible until the TTL lapses or the cache is dropped.
        await _seed_bank(session, "ESUN", "玉山銀行")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

    async def test_invalidate_forces_refetch(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        await fetch_bank_names(session)
        await _seed_bank(session, "ESUN", "玉山銀行")

        invalidate_bank_names_cache()

        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }

    async def test_ttl_expiry_refetches(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        await fetch_bank_names(session)
        await _seed_bank(session, "ESUN", "玉山銀行")

        _expire_cache_entry()

        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }

    async def test_returned_dict_is_a_copy(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        first = await fetch_bank_names(session)
        first["HACK"] = "mutated"

        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}


class TestSyncBankConfigsInvalidation:
    async def test_apply_sync_drops_cache(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        await fetch_bank_names(session)  # warm the cache

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
