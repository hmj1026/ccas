"""Tests for ccas.tools.seed_bank_settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import BankSettings, Base
from ccas.tools.seed_bank_settings import seed_bank_settings_from_yaml


def _write_banks_yaml(path: Path, codes: list[str]) -> None:
    body = "banks:\n" + "".join(
        f"  - bank_code: {c}\n    bank_name: {c} Bank\n    gmail_filter: 'from:{c}'\n"
        for c in codes
    )
    path.write_text(body, encoding="utf-8")


@pytest.fixture
async def in_memory_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


class TestSeedFromYaml:
    async def test_first_seed_inserts_one_row_per_bank(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        _write_banks_yaml(yaml_path, ["CTBC", "FUBON", "ESUN"])

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 3
        async with in_memory_session_factory() as session:
            result = await session.execute(select(BankSettings))
            rows = result.scalars().all()
        codes = {r.code for r in rows}
        assert codes == {"CTBC", "FUBON", "ESUN"}
        # default enabled=True
        assert all(r.enabled for r in rows)
        # display_name takes bank_name from yaml ("{CODE} Bank" by helper)
        by_code = {r.code: r for r in rows}
        for c in codes:
            assert by_code[c].display_name == f"{c} Bank"

    async def test_user_modified_rows_are_not_overwritten(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        _write_banks_yaml(yaml_path, ["CTBC", "FUBON"])

        # First seed.
        async with in_memory_session_factory() as session:
            await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        # User disables CTBC.
        async with in_memory_session_factory() as session:
            row = (
                await session.execute(
                    select(BankSettings).where(BankSettings.code == "CTBC")
                )
            ).scalar_one()
            row.enabled = False
            await session.commit()

        # Re-seed (e.g. container restart).
        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 0  # nothing new

        async with in_memory_session_factory() as session:
            row = (
                await session.execute(
                    select(BankSettings).where(BankSettings.code == "CTBC")
                )
            ).scalar_one()
        assert row.enabled is False  # user's choice preserved

    async def test_lowercase_bank_code_is_normalized_to_upper(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text(
            "banks:\n"
            "  - bank_code: ctbc\n"
            "    bank_name: CTBC\n"
            "    gmail_filter: 'from:ctbc'\n",
            encoding="utf-8",
        )

        async with in_memory_session_factory() as session:
            await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()
            row = (
                await session.execute(
                    select(BankSettings).where(BankSettings.code == "CTBC")
                )
            ).scalar_one_or_none()

        assert row is not None
        assert row.code == "CTBC"

    async def test_missing_yaml_returns_zero_without_raising(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(
                session, tmp_path / "does-not-exist.yaml"
            )
            await session.commit()

        assert inserted == 0
