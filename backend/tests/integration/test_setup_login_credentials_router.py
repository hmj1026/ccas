"""Integration tests for /api/setup/login-credentials/* endpoints (P3-7).

Mirrors test_setup_secrets_router.py: encrypt-at-rest, no plaintext/ciphertext
leakage, DB>env precedence, import-from-env idempotency. Also covers the
``resolve_bank_credential`` resolver (DB-first decrypt, env fallback,
master.key mismatch).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.errors import IngestError
from ccas.ingestor.credentials import resolve_bank_credential
from ccas.storage.models import BankLoginCredential
from ccas.storage.secrets import MasterKeyManager
from tests.integration.conftest import auth_headers

_NID = "A123456789"
_BIRTHDAY = "0801010"


@pytest.fixture
async def creds_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncGenerator[Path, None]:
    """Isolated master.key path + suppress any leaked FUBON_* from repo .env."""
    master_key = tmp_path / "master.key"
    get_settings.cache_clear()
    monkeypatch.setenv("MASTER_KEY_PATH", str(master_key))
    for key in ("FUBON_NATIONAL_ID", "FUBON_ROC_BIRTHDAY"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield master_key
    get_settings.cache_clear()


class TestListLoginCredentials:
    async def test_registry_creds_default_to_none_source(
        self, client: AsyncClient, creds_env: Path
    ) -> None:
        resp = await client.get("/api/setup/login-credentials", headers=auth_headers())
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]
        nid = next(
            i
            for i in items
            if i["bank_code"] == "FUBON" and i["credential_key"] == "NATIONAL_ID"
        )
        assert nid["has_db_value"] is False
        assert nid["has_env_value"] is False
        assert nid["effective_source"] == "none"

    async def test_env_only_marked_env(
        self,
        client: AsyncClient,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_NATIONAL_ID", _NID)
        get_settings.cache_clear()

        resp = await client.get("/api/setup/login-credentials", headers=auth_headers())
        item = next(
            i for i in resp.json()["data"] if i["credential_key"] == "NATIONAL_ID"
        )
        assert item["has_env_value"] is True
        assert item["has_db_value"] is False
        assert item["effective_source"] == "env"
        # Plaintext must never leak.
        assert _NID not in resp.text

    async def test_db_overrides_env_and_hides_secrets(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_NATIONAL_ID", _NID)
        get_settings.cache_clear()
        settings = get_settings()
        cipher = settings.master_key_manager.encrypt("db-nid")
        db_session.add(
            BankLoginCredential(
                bank_code="FUBON",
                credential_key="NATIONAL_ID",
                encrypted_value=cipher,
            )
        )
        await db_session.commit()

        resp = await client.get("/api/setup/login-credentials", headers=auth_headers())
        item = next(
            i for i in resp.json()["data"] if i["credential_key"] == "NATIONAL_ID"
        )
        assert item["effective_source"] == "db"
        assert item["has_db_value"] is True
        assert item["has_env_value"] is True
        assert _NID not in resp.text
        assert "db-nid" not in resp.text
        assert cipher not in resp.text

    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/setup/login-credentials")
        assert resp.status_code == 401


class TestUpsertLoginCredential:
    async def test_encrypts_and_stores(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
    ) -> None:
        resp = await client.put(
            "/api/setup/login-credentials/fubon/national_id",
            json={"value": _NID},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["bank_code"] == "FUBON"
        assert body["credential_key"] == "NATIONAL_ID"
        assert body["effective_source"] == "db"
        # Response never leaks plaintext.
        assert _NID not in resp.text

        row = await db_session.get(BankLoginCredential, ("FUBON", "NATIONAL_ID"))
        assert row is not None
        # Stored value is ciphertext, not plaintext.
        assert row.encrypted_value != _NID
        assert get_settings().master_key_manager.decrypt(row.encrypted_value) == _NID

    async def test_rejects_empty_value(
        self, client: AsyncClient, creds_env: Path
    ) -> None:
        resp = await client.put(
            "/api/setup/login-credentials/fubon/national_id",
            json={"value": ""},
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_rejects_unknown_credential_combo(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
    ) -> None:
        # Not in BANK_LOGIN_CREDENTIAL_KEYS → rejected, no orphan row written.
        resp = await client.put(
            "/api/setup/login-credentials/notabank/some_key",
            json={"value": "x"},
            headers=auth_headers(),
        )
        assert resp.status_code == 422
        assert (
            await db_session.get(BankLoginCredential, ("NOTABANK", "SOME_KEY")) is None
        )

    async def test_upsert_overwrites_existing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
    ) -> None:
        for value in ("old", "new"):
            await client.put(
                "/api/setup/login-credentials/fubon/roc_birthday",
                json={"value": value},
                headers=auth_headers(),
            )
        row = await db_session.get(BankLoginCredential, ("FUBON", "ROC_BIRTHDAY"))
        assert row is not None
        assert get_settings().master_key_manager.decrypt(row.encrypted_value) == "new"


class TestDeleteLoginCredential:
    async def test_delete_removes_row_env_remains(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_NATIONAL_ID", _NID)
        get_settings.cache_clear()
        cipher = get_settings().master_key_manager.encrypt("db-nid")
        db_session.add(
            BankLoginCredential(
                bank_code="FUBON",
                credential_key="NATIONAL_ID",
                encrypted_value=cipher,
            )
        )
        await db_session.commit()

        resp = await client.delete(
            "/api/setup/login-credentials/fubon/national_id",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        # Env fallback still active after DB row removed.
        assert resp.json()["data"]["effective_source"] == "env"
        assert (
            await db_session.get(BankLoginCredential, ("FUBON", "NATIONAL_ID")) is None
        )

    async def test_delete_missing_is_idempotent(
        self, client: AsyncClient, creds_env: Path
    ) -> None:
        resp = await client.delete(
            "/api/setup/login-credentials/fubon/national_id",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["effective_source"] == "none"


class TestImportFromEnv:
    async def test_imports_registry_env_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_NATIONAL_ID", _NID)
        monkeypatch.setenv("FUBON_ROC_BIRTHDAY", _BIRTHDAY)
        get_settings.cache_clear()

        resp = await client.post(
            "/api/setup/login-credentials/import-from-env",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["imported"] == 2
        assert set(data["credentials_imported"]) == {
            "FUBON_NATIONAL_ID",
            "FUBON_ROC_BIRTHDAY",
        }
        # Both rows decrypt back to the env plaintext.
        nid = await db_session.get(BankLoginCredential, ("FUBON", "NATIONAL_ID"))
        assert nid is not None
        assert get_settings().master_key_manager.decrypt(nid.encrypted_value) == _NID

    async def test_import_is_idempotent(
        self,
        client: AsyncClient,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_NATIONAL_ID", _NID)
        get_settings.cache_clear()

        first = await client.post(
            "/api/setup/login-credentials/import-from-env",
            headers=auth_headers(),
        )
        assert first.json()["data"]["imported"] == 1
        second = await client.post(
            "/api/setup/login-credentials/import-from-env",
            headers=auth_headers(),
        )
        assert second.json()["data"]["imported"] == 0
        assert second.json()["data"]["skipped_already_in_db"] == 1


class TestResolveBankCredential:
    async def test_db_first_decrypts(
        self,
        db_session: AsyncSession,
        creds_env: Path,
    ) -> None:
        settings = get_settings()
        cipher = settings.master_key_manager.encrypt(_NID)
        db_session.add(
            BankLoginCredential(
                bank_code="FUBON",
                credential_key="NATIONAL_ID",
                encrypted_value=cipher,
            )
        )
        await db_session.commit()

        value = await resolve_bank_credential(
            db_session, settings, "FUBON", "NATIONAL_ID"
        )
        assert value == _NID

    async def test_env_fallback_when_no_db_row(
        self,
        db_session: AsyncSession,
        creds_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FUBON_ROC_BIRTHDAY", _BIRTHDAY)
        get_settings.cache_clear()
        settings = get_settings()

        value = await resolve_bank_credential(
            db_session, settings, "FUBON", "ROC_BIRTHDAY"
        )
        assert value == _BIRTHDAY

    async def test_returns_none_when_absent(
        self, db_session: AsyncSession, creds_env: Path
    ) -> None:
        value = await resolve_bank_credential(
            db_session, get_settings(), "FUBON", "NATIONAL_ID"
        )
        assert value is None

    async def test_master_key_mismatch_raises_ingest_error(
        self,
        db_session: AsyncSession,
        creds_env: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Encrypt with a DIFFERENT master key, then resolve with the active one.
        other_key_path = tmp_path / "other.key"
        other_mgr = MasterKeyManager(other_key_path)
        other_mgr.load_or_create()
        foreign_cipher = other_mgr.encrypt(_NID)
        db_session.add(
            BankLoginCredential(
                bank_code="FUBON",
                credential_key="NATIONAL_ID",
                encrypted_value=foreign_cipher,
            )
        )
        await db_session.commit()

        with pytest.raises(IngestError):
            await resolve_bank_credential(
                db_session, get_settings(), "FUBON", "NATIONAL_ID"
            )
