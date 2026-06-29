"""Tests for ccas.tools.seed_bank_settings."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ccas.tools.seed_bank_settings as seed_mod
from ccas.storage.models import BankSettings, Base
from ccas.tools.seed_bank_settings import (
    _resolve_default_yaml_path,
    main,
    seed_bank_settings_from_yaml,
)


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

    async def test_malformed_yaml_returns_zero_without_raising(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text("banks: [unterminated\n", encoding="utf-8")

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 0

    async def test_non_mapping_root_returns_zero(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text("42\n", encoding="utf-8")

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 0

    async def test_banks_not_a_list_returns_zero(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text("banks: not-a-list\n", encoding="utf-8")

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 0

    async def test_skips_non_dict_and_codeless_rows(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text(
            "banks:\n"
            "  - just_a_string\n"  # not a dict -> skipped
            "  - bank_name: NoCode\n"  # missing bank_code -> skipped
            "  - bank_code: '   '\n"  # blank code -> skipped
            "  - bank_code: CTBC\n"
            "    bank_name: CTBC Bank\n",
            encoding="utf-8",
        )

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()
            rows = (await session.execute(select(BankSettings))).scalars().all()

        assert inserted == 1
        assert {r.code for r in rows} == {"CTBC"}

    async def test_no_valid_entries_returns_zero(
        self, tmp_path: Path, in_memory_session_factory
    ) -> None:
        yaml_path = tmp_path / "banks.yaml"
        yaml_path.write_text("banks:\n  - bank_name: HasNoCode\n", encoding="utf-8")

        async with in_memory_session_factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()

        assert inserted == 0


class TestResolveDefaultYamlPath:
    def test_uses_env_dir_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BANK_CONFIG_DIR", "/srv/config/")
        assert _resolve_default_yaml_path() == Path("/srv/config/banks.yaml")

    def test_falls_back_to_relative_path_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BANK_CONFIG_DIR", raising=False)
        assert _resolve_default_yaml_path() == Path("../config/banks.yaml")


async def _surviving_codes(url: str) -> set[str]:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        rows = (await session.execute(select(BankSettings))).scalars().all()
    await engine.dispose()
    return {r.code for r in rows}


class TestCli:
    def test_main_with_database_url_seeds_and_disposes_engine(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "seed.db"
        url = f"sqlite+aiosqlite:///{db_path}"

        async def _create_tables() -> None:
            engine = create_async_engine(url)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(_create_tables())

        yaml_path = tmp_path / "banks.yaml"
        _write_banks_yaml(yaml_path, ["CTBC", "FUBON"])

        rc = main(["--config", str(yaml_path), "--database-url", url])

        assert rc == 0
        assert "inserted=2" in capsys.readouterr().out
        assert asyncio.run(_surviving_codes(url)) == {"CTBC", "FUBON"}

    async def test_run_cli_default_branch_uses_module_singletons(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        monkeypatch.setattr(seed_mod, "get_engine", lambda: engine)
        monkeypatch.setattr(seed_mod, "get_session_factory", lambda: factory)

        yaml_path = tmp_path / "banks.yaml"
        _write_banks_yaml(yaml_path, ["ESUN"])

        rc = await seed_mod._run_cli(yaml_path, None)

        assert rc == 0
        assert "inserted=1" in capsys.readouterr().out
        # owns_engine is False here: engine NOT disposed, still usable.
        async with factory() as session:
            rows = (await session.execute(select(BankSettings))).scalars().all()
        assert {r.code for r in rows} == {"ESUN"}
        await engine.dispose()
