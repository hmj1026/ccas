"""Session cookie HMAC encode/decode 單元測試（session-cookie-hmac）。

驗證 ``{version}.{timestamp}.{hmac}`` opaque cookie 的三重檢查：
HMAC 簽章、token version、有效期（``api_session_max_age``）。
"""

import base64
import time
from pathlib import Path

import pytest

from ccas.api.deps import (
    current_api_token_version,
    decode_session_cookie,
    encode_session_cookie,
    is_valid_session_cookie,
)
from ccas.config import get_settings

_TOKEN = "test-api-token"  # matches unit conftest API_TOKEN


@pytest.fixture(autouse=True)
def _isolated_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolated master.key + api-token-version files per test."""
    import ccas.api.deps as _deps

    # Reset the module-level derived-secret cache: low-resolution mtime
    # filesystems could otherwise let a previous test's secret leak through.
    _deps._session_secret_cache = None
    monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "master.key"))
    version_file = tmp_path / "api-token-version"
    version_file.write_text("1")
    monkeypatch.setenv("API_TOKEN_VERSION_PATH", str(version_file))
    get_settings.cache_clear()
    yield
    _deps._session_secret_cache = None


class TestEncodeDecodeRoundtrip:
    async def test_valid_cookie_roundtrip(self):
        cookie = encode_session_cookie(_TOKEN, current_api_token_version())
        decoded = decode_session_cookie(cookie)
        assert decoded is not None
        version, issued_at, mac = decoded
        assert version == 1
        assert abs(int(time.time()) - issued_at) <= 2
        assert len(mac) == 64  # sha256 hexdigest
        assert is_valid_session_cookie(cookie)

    async def test_plaintext_token_not_in_cookie(self):
        cookie = encode_session_cookie(_TOKEN, current_api_token_version())
        assert _TOKEN not in cookie
        assert base64.b64encode(_TOKEN.encode()).decode() not in cookie


class TestDecodeRejectsMalformed:
    async def test_none_and_empty(self):
        assert decode_session_cookie(None) is None
        assert decode_session_cookie("") is None

    async def test_wrong_part_count(self):
        assert decode_session_cookie("1.123") is None
        assert decode_session_cookie("1.123.abc.def") is None

    async def test_non_numeric_fields(self):
        assert decode_session_cookie("v1.123.abc") is None
        assert decode_session_cookie("1.now.abc") is None
        assert decode_session_cookie("1.123.") is None

    async def test_legacy_base64_json_cookie(self):
        legacy = base64.urlsafe_b64encode(b'{"token": "x", "version": 1}').decode()
        assert decode_session_cookie(legacy) is None

    async def test_oversized_cookie_rejected(self):
        assert decode_session_cookie("1.1." + "a" * 2048) is None


class TestValidationRejects:
    async def test_tampered_hmac(self):
        cookie = encode_session_cookie(_TOKEN, current_api_token_version())
        version, ts, mac = cookie.split(".")
        flipped = ("0" if mac[-1] != "0" else "1") + mac[1:]
        assert not is_valid_session_cookie(f"{version}.{ts}.{flipped}")

    async def test_tampered_timestamp(self):
        cookie = encode_session_cookie(_TOKEN, current_api_token_version())
        version, ts, mac = cookie.split(".")
        assert not is_valid_session_cookie(f"{version}.{int(ts) + 1}.{mac}")

    async def test_expired_timestamp(self):
        max_age = get_settings().api_session_max_age
        stale = int(time.time()) - max_age - 1
        cookie = encode_session_cookie(
            _TOKEN, current_api_token_version(), issued_at=stale
        )
        assert not is_valid_session_cookie(cookie)

    async def test_future_timestamp_rejected(self):
        cookie = encode_session_cookie(
            _TOKEN, current_api_token_version(), issued_at=int(time.time()) + 3600
        )
        assert not is_valid_session_cookie(cookie)

    async def test_wrong_token_signature(self):
        cookie = encode_session_cookie("not-the-real-token", 1)
        assert not is_valid_session_cookie(cookie)

    async def test_version_bump_invalidates_old_cookie(self, tmp_path: Path):
        cookie = encode_session_cookie(_TOKEN, current_api_token_version())
        assert is_valid_session_cookie(cookie)
        # Simulate POST /api/setup/admin/token-rotate bumping the version file.
        (tmp_path / "api-token-version").write_text("2")
        assert current_api_token_version() == 2
        assert not is_valid_session_cookie(cookie)
