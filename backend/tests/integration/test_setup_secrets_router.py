"""Integration tests for /api/setup/secrets/* endpoints (oauth-onboarding-ui §5)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.storage.models import BankConfig, BankSecret
from tests.integration.conftest import auth_headers


@pytest.fixture
async def secrets_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncGenerator[Path, None]:
    """Isolated master.key path per test + clean Settings cache.

    Suppresses any ``PDF_PASSWORD_*`` value that may leak from the developer's
    repo-root ``.env``. We scan the live ``Settings._env_map`` to catch every
    such key (including ones added in future), then ``setenv("", "")`` so
    ``os.environ`` overrides the ``.env`` value with a falsy string — the
    production scanner treats falsy as absent.
    """
    master_key = tmp_path / "master.key"
    get_settings.cache_clear()
    monkeypatch.setenv("MASTER_KEY_PATH", str(master_key))
    leaked_keys = [k for k in get_settings()._env_map if k.startswith("PDF_PASSWORD_")]
    for key in leaked_keys:
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield master_key
    get_settings.cache_clear()


def _make_config(code: str) -> BankConfig:
    return BankConfig(
        bank_code=code,
        bank_name=f"{code} Bank",
        gmail_filter=f"from:{code.lower()}@example.com",
    )


class TestListSecrets:
    async def test_lists_all_known_banks_with_none_source_when_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()

        resp = await client.get("/api/setup/secrets", headers=auth_headers())

        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]
        ctbc = next(i for i in items if i["bank_code"] == "CTBC")
        assert ctbc["has_db_secret"] is False
        assert ctbc["has_env_secret"] is False
        assert ctbc["effective_source"] == "none"

    async def test_env_only_marked_env(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_session.add(_make_config("ESUN"))
        await db_session.commit()
        monkeypatch.setenv("PDF_PASSWORD_ESUN", "env-pw")
        get_settings.cache_clear()

        resp = await client.get("/api/setup/secrets", headers=auth_headers())
        item = next(i for i in resp.json()["data"] if i["bank_code"] == "ESUN")
        assert item["has_env_secret"] is True
        assert item["has_db_secret"] is False
        assert item["effective_source"] == "env"

    async def test_db_overrides_env_in_effective_source(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "env-pw")
        get_settings.cache_clear()
        settings = get_settings()
        cipher = settings.master_key_manager.encrypt("db-pw")
        db_session.add(BankSecret(bank_code="CTBC", encrypted_password=cipher))
        await db_session.commit()

        resp = await client.get("/api/setup/secrets", headers=auth_headers())
        item = next(i for i in resp.json()["data"] if i["bank_code"] == "CTBC")
        assert item["effective_source"] == "db"
        assert item["has_db_secret"] is True
        assert item["has_env_secret"] is True
        # CRITICAL: response must not leak plaintext or ciphertext.
        assert "env-pw" not in resp.text
        assert "db-pw" not in resp.text
        assert cipher not in resp.text

    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/setup/secrets")
        assert resp.status_code == 401


class TestUpsertSecret:
    async def test_creates_db_row_and_does_not_return_plaintext(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()

        resp = await client.put(
            "/api/setup/secrets/CTBC",
            json={"password": "super-secret-pw"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"]["effective_source"] == "db"
        assert "super-secret-pw" not in resp.text

        row = await db_session.get(BankSecret, "CTBC")
        assert row is not None
        # Stored value must be encrypted, not plaintext.
        assert row.encrypted_password != "super-secret-pw"

    async def test_replaces_existing_row_on_repeat_put(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()

        await client.put(
            "/api/setup/secrets/CTBC",
            json={"password": "first"},
            headers=auth_headers(),
        )
        await client.put(
            "/api/setup/secrets/CTBC",
            json={"password": "second"},
            headers=auth_headers(),
        )

        # Decrypt and confirm second value won.
        settings = get_settings()
        row = await db_session.get(BankSecret, "CTBC")
        assert row is not None
        assert settings.master_key_manager.decrypt(row.encrypted_password) == "second"

    async def test_normalizes_code_to_upper(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()

        resp = await client.put(
            "/api/setup/secrets/ctbc",
            json={"password": "pw"},
            headers=auth_headers(),
        )

        assert resp.status_code == 200
        assert (await db_session.get(BankSecret, "CTBC")) is not None

    async def test_requires_auth(self, client: AsyncClient, secrets_env: Path) -> None:
        resp = await client.put("/api/setup/secrets/CTBC", json={"password": "pw"})
        assert resp.status_code == 401

    async def test_rejects_invalid_bank_code(
        self, client: AsyncClient, db_session: AsyncSession, secrets_env: Path
    ) -> None:
        """格式白名單：非 [A-Z0-9_-] 的 code 應回 422，不得寫入任意 Unicode。"""
        resp = await client.put(
            "/api/setup/secrets/CT.BC",
            json={"password": "pw"},
            headers=auth_headers(),
        )
        assert resp.status_code == 422
        # 不得有任何 BankSecret 列被寫入
        assert (await db_session.get(BankSecret, "CT.BC")) is None

    async def test_rejects_oversized_bank_code(
        self, client: AsyncClient, secrets_env: Path
    ) -> None:
        """超過 bank_code 欄位寬度（32）應回 422，不得靜默截斷。"""
        resp = await client.put(
            f"/api/setup/secrets/{'A' * 33}",
            json={"password": "pw"},
            headers=auth_headers(),
        )
        assert resp.status_code == 422


class TestDeleteSecret:
    async def test_deletes_existing_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
    ) -> None:
        settings = get_settings()
        cipher = settings.master_key_manager.encrypt("pw")
        db_session.add(_make_config("CTBC"))
        db_session.add(BankSecret(bank_code="CTBC", encrypted_password=cipher))
        await db_session.commit()

        resp = await client.delete("/api/setup/secrets/CTBC", headers=auth_headers())
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert (await db_session.get(BankSecret, "CTBC")) is None

    async def test_delete_missing_row_is_idempotent(
        self,
        client: AsyncClient,
        secrets_env: Path,
    ) -> None:
        resp = await client.delete("/api/setup/secrets/UNKNOWN", headers=auth_headers())
        assert resp.status_code == 200


class TestImportFromEnv:
    async def test_imports_env_secrets_skipping_existing_db_rows(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_session.add_all([_make_config("CTBC"), _make_config("ESUN")])
        await db_session.commit()
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "ctbc-env")
        monkeypatch.setenv("PDF_PASSWORD_ESUN", "esun-env")
        monkeypatch.setenv("PDF_PASSWORD_FOO_LEGACY_1", "should-be-ignored")
        get_settings.cache_clear()

        # Pre-populate one DB row to verify it is skipped.
        settings = get_settings()
        db_session.add(
            BankSecret(
                bank_code="ESUN",
                encrypted_password=settings.master_key_manager.encrypt("existing"),
            )
        )
        await db_session.commit()

        resp = await client.post(
            "/api/setup/secrets/import-from-env", headers=auth_headers()
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["imported"] == 1
        assert body["skipped_already_in_db"] == 1
        assert body["bank_codes_imported"] == ["CTBC"]

        # Decrypt to verify CTBC stored env value, ESUN preserved.
        ctbc_row = await db_session.get(BankSecret, "CTBC")
        esun_row = await db_session.get(BankSecret, "ESUN")
        assert ctbc_row is not None
        assert esun_row is not None
        assert (
            settings.master_key_manager.decrypt(ctbc_row.encrypted_password)
            == "ctbc-env"
        )
        assert (
            settings.master_key_manager.decrypt(esun_row.encrypted_password)
            == "existing"
        )

    async def test_idempotent_when_run_twice(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "pw")
        get_settings.cache_clear()

        first = await client.post(
            "/api/setup/secrets/import-from-env", headers=auth_headers()
        )
        second = await client.post(
            "/api/setup/secrets/import-from-env", headers=auth_headers()
        )
        assert first.json()["data"]["imported"] == 1
        assert second.json()["data"]["imported"] == 0
        assert second.json()["data"]["skipped_already_in_db"] == 1

    async def test_response_does_not_leak_passwords(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        secrets_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_session.add(_make_config("CTBC"))
        await db_session.commit()
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "topsecretpw")
        get_settings.cache_clear()

        resp = await client.post(
            "/api/setup/secrets/import-from-env", headers=auth_headers()
        )

        assert "topsecretpw" not in resp.text
