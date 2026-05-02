"""Integration tests for /api/setup/admin/* endpoints (oauth-onboarding-ui §6).

Covers:
- ``GET /api/setup/admin/token-info``: returns last4 + created_at + version,
  never the full token.
- ``POST /api/setup/admin/token-rotate``: returns the new full token exactly
  once, bumps the on-disk version file, and invalidates any pre-rotate
  Bearer / cookie credentials.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient

from ccas.config import get_settings
from tests.integration.conftest import auth_headers


@pytest.fixture
async def admin_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncGenerator[Path, None]:
    """Isolated api-token / api-token-version files per test.

    Pre-seeds both files with a known token + version=1 so a fresh integration
    client can authenticate against them. Tests that exercise rotation read
    these files back to verify the rotate endpoint wrote new contents.
    """
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    token_file = secrets_dir / "api-token"
    version_file = secrets_dir / "api-token-version"
    token_file.write_text("test-token")
    version_file.write_text("1")

    get_settings.cache_clear()
    monkeypatch.setenv("API_TOKEN_PATH", str(token_file))
    monkeypatch.setenv("API_TOKEN_VERSION_PATH", str(version_file))
    get_settings.cache_clear()
    yield secrets_dir
    get_settings.cache_clear()


class TestTokenInfo:
    async def test_returns_last4_and_version_without_full_token(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        resp = await client.get("/api/setup/admin/token-info", headers=auth_headers())
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["last4"] == "oken"  # last 4 chars of "test-token"
        assert data["version"] == 1
        assert "created_at" in data
        assert "test-token" not in resp.text

    async def test_requires_auth(self, client: AsyncClient, admin_env: Path) -> None:
        resp = await client.get("/api/setup/admin/token-info")
        assert resp.status_code == 401


class TestTokenRotate:
    async def test_rotate_writes_new_token_and_bumps_version(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        resp = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        new_token = body["token"]
        assert isinstance(new_token, str) and len(new_token) >= 32
        assert body["version"] == 2
        assert body["last4"] == new_token[-4:]

        token_file = admin_env / "api-token"
        version_file = admin_env / "api-token-version"
        assert token_file.read_text().strip() == new_token
        assert version_file.read_text().strip() == "2"

    async def test_old_bearer_token_rejected_after_rotate(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        rotate_resp = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        assert rotate_resp.status_code == 200
        # Old token must now be 401.
        resp = await client.get(
            "/api/setup/admin/token-info", headers=auth_headers("test-token")
        )
        assert resp.status_code == 401

    async def test_new_bearer_token_works_after_rotate(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        rotate_resp = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        new_token = rotate_resp.json()["data"]["token"]
        resp = await client.get(
            "/api/setup/admin/token-info", headers=auth_headers(new_token)
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["last4"] == new_token[-4:]
        assert resp.json()["data"]["version"] == 2

    async def test_old_session_cookie_rejected_after_rotate(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        # Establish a session cookie under version=1.
        login = await client.post("/api/auth/session", json={"token": "test-token"})
        assert login.status_code == 204
        # Confirm cookie works pre-rotate.
        pre = await client.get("/api/setup/admin/token-info")
        assert pre.status_code == 200, pre.text
        # Rotate via Bearer header (cookie still version=1).
        rotate = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        assert rotate.status_code == 200
        # Cookie embedded version=1, current file version=2 → must reject.
        resp = await client.get("/api/setup/admin/token-info")
        assert resp.status_code == 401

    async def test_two_rotations_in_a_row_increment_version(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        first = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        first_token = first.json()["data"]["token"]
        second = await client.post(
            "/api/setup/admin/token-rotate",
            headers=auth_headers(first_token),
        )
        assert first.json()["data"]["version"] == 2
        assert second.json()["data"]["version"] == 3
        version_file = admin_env / "api-token-version"
        assert version_file.read_text().strip() == "3"

    async def test_rotate_requires_auth(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        resp = await client.post("/api/setup/admin/token-rotate")
        assert resp.status_code == 401

    async def test_rotate_response_has_no_store_cache_control(
        self,
        client: AsyncClient,
        admin_env: Path,
    ) -> None:
        """Plaintext token in the body must not be cacheable (sec H2)."""
        resp = await client.post(
            "/api/setup/admin/token-rotate", headers=auth_headers()
        )
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"
