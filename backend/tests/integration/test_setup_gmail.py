"""Integration tests for /api/setup/gmail/* endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.storage.models import GmailOAuthState
from ccas.storage.oauth_secrets import read_token_payload
from tests.integration.conftest import auth_headers


@pytest.fixture
async def gmail_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncGenerator[tuple[Path, Path], None]:
    """Redirect Gmail credentials/token paths to a temp dir for the test.

    Clears ``get_settings`` lru_cache both before AND after env mutation so
    that any prior test's cached Settings instance is discarded and the
    handler's ``Depends(get_settings)`` rebuilds with the patched env.
    """
    creds = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    get_settings.cache_clear()
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(creds))
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(token))
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8080")
    # Stage 6 A3: OAuth creds are encrypted at rest with master.key; point the
    # key into tmp so the test never writes into the repo's ./data/secrets.
    monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "secrets" / "master.key"))
    get_settings.cache_clear()
    yield creds, token
    get_settings.cache_clear()


def _read_oauth_file(path: Path) -> dict[str, Any]:
    """Decrypt an on-disk OAuth file the way the router's read path does."""
    return read_token_payload(path, get_settings().master_key_manager)


def _valid_credentials_payload() -> dict[str, Any]:
    return {
        "web": {
            "client_id": "1234567890-abc.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/setup/gmail/callback"],
        }
    }


class TestUploadCredentials:
    async def test_upload_valid_web_credentials_writes_file(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        creds_path, _ = gmail_paths
        payload = _valid_credentials_payload()
        files = {
            "file": (
                "credentials.json",
                json.dumps(payload).encode(),
                "application/json",
            )
        }

        resp = await client.post(
            "/api/setup/gmail/credentials",
            files=files,
            headers=auth_headers(),
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["client_id_last8"] == "leusercontent.com"[-8:]
        assert creds_path.exists()
        assert creds_path.stat().st_mode & 0o777 == 0o600
        # Stage 6 A3: file is encrypted at rest — the client_secret must NOT
        # appear in cleartext, but the decrypt read path round-trips the payload.
        on_disk = creds_path.read_text()
        assert "GOCSPX-test-secret" not in on_disk
        assert json.loads(on_disk)["ccas_enc"] is not None  # envelope, not payload
        assert _read_oauth_file(creds_path) == payload

    async def test_upload_rejects_non_json_body(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        files = {"file": ("credentials.json", b"not json", "application/json")}
        resp = await client.post(
            "/api/setup/gmail/credentials",
            files=files,
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_upload_rejects_oversized_file(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        """Bodies above 1 MB are rejected with 413 before JSON parsing."""
        files = {
            "file": (
                "credentials.json",
                b"x" * 1_000_001,
                "application/json",
            )
        }
        resp = await client.post(
            "/api/setup/gmail/credentials",
            files=files,
            headers=auth_headers(),
        )
        assert resp.status_code == 413
        # HTTPException is wrapped into the unified {success, message, data} envelope.
        assert "1 MB" in resp.json()["message"]

    async def test_upload_rejects_missing_client_secret(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        payload = {"web": {"client_id": "abc.apps.googleusercontent.com"}}
        files = {
            "file": (
                "credentials.json",
                json.dumps(payload).encode(),
                "application/json",
            )
        }
        resp = await client.post(
            "/api/setup/gmail/credentials",
            files=files,
            headers=auth_headers(),
        )
        assert resp.status_code == 422


class TestAuthorize:
    async def test_authorize_returns_url_and_persists_state(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        creds_path, _ = gmail_paths
        creds_path.write_text(json.dumps(_valid_credentials_payload()))
        creds_path.chmod(0o600)

        resp = await client.get(
            "/api/setup/gmail/authorize",
            headers=auth_headers(),
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["authorize_url"].startswith("https://accounts.google.com/o/oauth2/")
        assert "code_challenge" in data["authorize_url"]
        assert "code_challenge_method=S256" in data["authorize_url"]
        assert "state=" in data["authorize_url"]
        assert data["state"]
        # State persisted in DB.
        rows = (await db_session.execute(select(GmailOAuthState))).scalars().all()
        assert any(r.state == data["state"] for r in rows)

    async def test_authorize_fails_without_credentials(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        resp = await client.get(
            "/api/setup/gmail/authorize",
            headers=auth_headers(),
        )
        assert resp.status_code == 400


class TestCallback:
    async def test_callback_with_unknown_state_returns_422(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        # Unknown/used OAuth state is invalid input → 422 (aligns with the
        # 422 input-validation convention in budgets/rules/transactions).
        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"code": "any", "state": "nonexistent-state"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 422

    async def test_callback_with_expired_state_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        creds_path, _ = gmail_paths
        creds_path.write_text(json.dumps(_valid_credentials_payload()))
        # Insert a state >10 minutes old.
        old_state = GmailOAuthState(
            state="expired-state-xyz",
            code_verifier="verifier-123",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(old_state)
        await db_session.commit()

        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"code": "any", "state": "expired-state-xyz"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 422
        # Expired-state message guides the user to retry the authorize flow.
        assert "請重新點擊授權按鈕" in resp.json()["message"]

    @respx.mock
    async def test_callback_happy_path_writes_token_and_redirects(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        creds_path, token_path = gmail_paths
        creds_path.write_text(json.dumps(_valid_credentials_payload()))
        creds_path.chmod(0o600)

        # Stub Google's token endpoint.
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(
                200,
                json={
                    "access_token": "ya29.fake-access",
                    "refresh_token": "1//fake-refresh",
                    "scope": "https://www.googleapis.com/auth/gmail.readonly",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )

        # Pre-insert state row (simulates prior /authorize call).
        live_state = GmailOAuthState(
            state="happy-state-1",
            code_verifier="verifier-happy",
            created_at=datetime.now(UTC),
        )
        db_session.add(live_state)
        await db_session.commit()

        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"code": "auth-code-from-google", "state": "happy-state-1"},
            headers=auth_headers(),
            follow_redirects=False,
        )

        assert resp.status_code in (302, 303, 307), resp.text
        assert "/setup/gmail" in resp.headers["location"]
        # Token file written (encrypted), state row deleted.
        assert token_path.exists()
        assert token_path.stat().st_mode & 0o777 == 0o600
        # Stage 6 A3: refresh_token is NOT plaintext on disk; decrypt to verify.
        on_disk = token_path.read_text()
        assert "1//fake-refresh" not in on_disk
        token_data = _read_oauth_file(token_path)
        assert token_data["refresh_token"] == "1//fake-refresh"
        rows = (await db_session.execute(select(GmailOAuthState))).scalars().all()
        assert all(r.state != "happy-state-1" for r in rows)

    async def test_callback_with_error_param_redirects_to_error_page(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        # User denies consent → Google redirects with ?error=access_denied and
        # NO code. Must become a friendly redirect (not a 422), without leaking
        # Google's raw error string into the result URL.
        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"error": "access_denied", "state": "any-state"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/setup/gmail" in location
        assert "status=error" in location
        assert "access_denied" not in location

    async def test_callback_without_code_or_error_returns_400(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        # A malformed callback (no code, no error) is a bad request (400), not a
        # validation 422 — keeps it distinct from the unknown-state 422 case.
        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"state": "any-state"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 400

    @respx.mock
    async def test_callback_token_exchange_failure_redirects_to_error(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        # The state is consumed before the exchange, so a failed exchange must
        # redirect to the frontend error page (not strand the user on a raw 4xx).
        creds_path, _ = gmail_paths
        creds_path.write_text(json.dumps(_valid_credentials_payload()))
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(400, json={"error": "invalid_grant"})
        )
        live_state = GmailOAuthState(
            state="fail-state-1",
            code_verifier="verifier-fail",
            created_at=datetime.now(UTC),
        )
        db_session.add(live_state)
        await db_session.commit()

        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"code": "bad-code", "state": "fail-state-1"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "status=error" in resp.headers["location"]
        # State consumed (deleted before exchange) even on failure.
        rows = (await db_session.execute(select(GmailOAuthState))).scalars().all()
        assert all(r.state != "fail-state-1" for r in rows)


class TestStatus:
    async def test_status_returns_disconnected_when_token_missing(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        resp = await client.get(
            "/api/setup/gmail/status",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["connected"] is False
        assert data["email"] is None

    async def test_status_returns_connected_when_token_present(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        _, token_path = gmail_paths
        token_path.write_text(
            json.dumps(
                {
                    "token": "ya29.fake",
                    "refresh_token": "1//fake",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                    "client_id": "abc",
                    "client_secret": "xyz",
                }
            )
        )

        resp = await client.get(
            "/api/setup/gmail/status",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["connected"] is True
        assert (
            "https://www.googleapis.com/auth/gmail.readonly" in data["granted_scopes"]
        )

    async def test_status_reads_legacy_plaintext_token(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        """既有 plaintext token.json（Stage 6 之前）仍回報 connected。"""
        _, token_path = gmail_paths
        # Plaintext, no encryption envelope — simulates a pre-upgrade deployment.
        token_path.write_text(
            json.dumps(
                {
                    "token": "ya29.legacy",
                    "refresh_token": "1//legacy",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                }
            )
        )

        resp = await client.get(
            "/api/setup/gmail/status",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["connected"] is True


class TestRevoke:
    @respx.mock
    async def test_revoke_deletes_token_and_calls_google(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        _, token_path = gmail_paths
        token_path.write_text(
            json.dumps(
                {
                    "token": "ya29.fake-revoke",
                    "refresh_token": "1//fake",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                }
            )
        )
        revoke_route = respx.post("https://oauth2.googleapis.com/revoke").mock(
            return_value=Response(200)
        )

        resp = await client.post(
            "/api/setup/gmail/revoke",
            headers=auth_headers(),
        )

        assert resp.status_code == 200
        assert not token_path.exists()
        assert revoke_route.called

    async def test_revoke_when_no_token_is_idempotent(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        resp = await client.post(
            "/api/setup/gmail/revoke",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
