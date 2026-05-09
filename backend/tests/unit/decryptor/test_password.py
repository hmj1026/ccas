"""密碼解析的單元測試（async / DB-first / env fallback）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.config import Settings
from ccas.decryptor.password import resolve_password, resolve_passwords
from ccas.errors import DecryptError
from ccas.storage.models import BankSecret, Base
from ccas.storage.secrets import MasterKeyManager


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def settings_with_master_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Settings:
    monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "master.key"))
    return Settings()  # pyright: ignore[reportCallIssue]


def _make_settings_with_envs(monkeypatch: pytest.MonkeyPatch, **envs: str) -> Settings:
    for k, v in envs.items():
        monkeypatch.setenv(k, v)
    return Settings()  # pyright: ignore[reportCallIssue]


class TestResolvePasswordEnvFallback:
    async def test_returns_env_password_when_no_db_row(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings_with_envs(monkeypatch, PDF_PASSWORD_CTBC="env-pw")
        async with session_factory() as session:
            result = await resolve_password(session, settings, "CTBC")
        assert result == "env-pw"

    async def test_returns_none_when_no_db_no_env(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Use a synthetic bank code that has no .env entry on any developer
        # machine, then guarantee no env override leaks in.
        monkeypatch.delenv("PDF_PASSWORD_NOPETESTBANK", raising=False)
        settings = Settings()  # pyright: ignore[reportCallIssue]
        async with session_factory() as session:
            result = await resolve_password(session, settings, "NOPETESTBANK")
        assert result is None

    async def test_case_insensitive_bank_code(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings_with_envs(monkeypatch, PDF_PASSWORD_CATHAY="x")
        async with session_factory() as session:
            assert await resolve_password(session, settings, "cathay") == "x"


class TestResolvePasswordDbFirst:
    async def test_db_row_wins_over_env(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "master.key"))
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "env-pw")
        settings = Settings()  # pyright: ignore[reportCallIssue]
        ciphertext = settings.master_key_manager.encrypt("db-pw")
        async with session_factory() as session:
            session.add(BankSecret(bank_code="CTBC", encrypted_password=ciphertext))
            await session.commit()
            result = await resolve_password(session, settings, "CTBC")
        assert result == "db-pw"

    async def test_db_row_decrypt_failure_raises_decrypt_error_with_clear_message(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Encrypt with one master.key, then point Settings at a different one.
        original_key_path = tmp_path / "original.key"
        wrong_key_path = tmp_path / "wrong.key"
        original_mgr = MasterKeyManager(original_key_path)
        ciphertext = original_mgr.encrypt("db-pw")

        monkeypatch.setenv("MASTER_KEY_PATH", str(wrong_key_path))
        settings = Settings()  # pyright: ignore[reportCallIssue]
        async with session_factory() as session:
            session.add(BankSecret(bank_code="CTBC", encrypted_password=ciphertext))
            await session.commit()
            with pytest.raises(DecryptError) as excinfo:
                await resolve_password(session, settings, "CTBC")
        assert "master.key" in str(excinfo.value)
        assert excinfo.value.context.get("bank_code") == "CTBC"


class TestResolvePasswords:
    async def test_db_primary_then_env_legacy(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "master.key"))
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "env-primary")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_1", "legacy-1")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_2", "legacy-2")
        settings = Settings()  # pyright: ignore[reportCallIssue]
        ciphertext = settings.master_key_manager.encrypt("db-primary")

        async with session_factory() as session:
            session.add(BankSecret(bank_code="TAISHIN", encrypted_password=ciphertext))
            await session.commit()
            result = await resolve_passwords(session, settings, "TAISHIN")

        # DB primary first; env primary skipped (different value, but appended
        # after legacies because it is part of env_chain after the primary).
        assert result[0] == "db-primary"
        assert "legacy-1" in result
        assert "legacy-2" in result

    async def test_env_only_returns_env_chain(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PDF_PASSWORD_ESUN", "env-primary")
        monkeypatch.setenv("PDF_PASSWORD_ESUN_LEGACY_1", "legacy-1")
        settings = Settings()  # pyright: ignore[reportCallIssue]

        async with session_factory() as session:
            result = await resolve_passwords(session, settings, "ESUN")

        assert result == ("env-primary", "legacy-1")

    async def test_returns_empty_when_nothing_set(
        self,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k in (
            "PDF_PASSWORD_UNKNOWN",
            "PDF_PASSWORD_UNKNOWN_LEGACY_1",
        ):
            monkeypatch.delenv(k, raising=False)
        settings = Settings()  # pyright: ignore[reportCallIssue]
        async with session_factory() as session:
            result = await resolve_passwords(session, settings, "UNKNOWN")
        assert result == ()
