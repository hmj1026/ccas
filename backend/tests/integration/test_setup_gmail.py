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
    get_settings.cache_clear()
    yield creds, token
    get_settings.cache_clear()


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
        # File must contain the original payload verbatim.
        assert json.loads(creds_path.read_text()) == payload

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
    async def test_callback_with_unknown_state_returns_400(
        self,
        client: AsyncClient,
        gmail_paths: tuple[Path, Path],
    ) -> None:
        resp = await client.get(
            "/api/setup/gmail/callback",
            params={"code": "any", "state": "nonexistent-state"},
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert resp.status_code == 400

    async def test_callback_with_expired_state_returns_400(
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
        assert resp.status_code == 400

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
        # Token file written, state row deleted.
        assert token_path.exists()
        assert token_path.stat().st_mode & 0o777 == 0o600
        token_data = json.loads(token_path.read_text())
        assert token_data["refresh_token"] == "1//fake-refresh"
        rows = (await db_session.execute(select(GmailOAuthState))).scalars().all()
        assert all(r.state != "happy-state-1" for r in rows)


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
