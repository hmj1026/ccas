"""OAuth 憑證載入與 token 自動刷新的單元測試。"""

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from ccas.ingestor.auth import (
    GmailAuthError,
    load_credentials,
    write_private_token_file,
)
from ccas.storage.oauth_secrets import write_encrypted_token_file
from ccas.storage.secrets import MasterKeyManager

_TOKEN_JSON = json.dumps(
    {
        "token": "ya29.fake-access",
        "refresh_token": "1//fake-refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "abc.apps.googleusercontent.com",
        "client_secret": "GOCSPX-fake-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
)


@pytest.fixture
def key_manager(tmp_path: Path) -> MasterKeyManager:
    """A MasterKeyManager backed by a fresh per-test master.key."""
    return MasterKeyManager(tmp_path / "secrets" / "master.key")


class TestWritePrivateTokenFile:
    """R15：token 檔須一落地即為 owner-only（0600），無 race window。"""

    def test_writes_content_with_owner_only_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "token.json"
        write_private_token_file(target, '{"token": "abc"}')

        assert target.read_text(encoding="utf-8") == '{"token": "abc"}'
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600, f"預期 0600，實得 {oct(mode)}"

    def test_overwrites_existing_token_and_keeps_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "token.json"
        write_private_token_file(target, "old")
        write_private_token_file(target, "new")

        assert target.read_text(encoding="utf-8") == "new"
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


class TestLoadCredentials:
    """load_credentials() 的測試案例（含 Stage 6 A3 加密 token 讀寫）。"""

    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_info")
    def test_valid_token_returns_credentials(
        self, mock_from_info, tmp_path: Path, key_manager: MasterKeyManager
    ):
        """token 有效時直接回傳 credentials，不呼叫 refresh。"""
        token_path = tmp_path / "token.json"
        write_encrypted_token_file(token_path, _TOKEN_JSON, key_manager)
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_from_info.return_value = mock_creds

        result = load_credentials("/creds.json", str(token_path), manager=key_manager)

        assert result is mock_creds
        # Decryption fed the parsed dict (not the encryption envelope) to google-auth.
        passed_info = mock_from_info.call_args.args[0]
        assert passed_info["refresh_token"] == "1//fake-refresh"
        mock_creds.refresh.assert_not_called()

    def test_reads_legacy_plaintext_token(
        self, tmp_path: Path, key_manager: MasterKeyManager
    ):
        """既有 plaintext token.json 仍可載入（向後相容）。"""
        token_path = tmp_path / "token.json"
        token_path.write_text(_TOKEN_JSON, encoding="utf-8")  # plaintext, no envelope

        with patch(
            "ccas.ingestor.auth.Credentials.from_authorized_user_info"
        ) as mock_from_info:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_from_info.return_value = mock_creds

            result = load_credentials(
                "/creds.json", str(token_path), manager=key_manager
            )

        assert result is mock_creds
        assert mock_from_info.call_args.args[0]["refresh_token"] == "1//fake-refresh"

    @patch("ccas.ingestor.auth.Request")
    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_info")
    def test_expired_token_auto_refreshes_and_rewrites_encrypted(
        self,
        mock_from_info,
        mock_request_cls,
        tmp_path: Path,
        key_manager: MasterKeyManager,
    ):
        """token 過期時自動 refresh() 並以加密格式回寫（refresh_token 不再明文）。"""
        token_path = tmp_path / "token.json"
        write_encrypted_token_file(token_path, _TOKEN_JSON, key_manager)

        refreshed_json = json.dumps(
            {"token": "ya29.refreshed", "refresh_token": "1//fake-refresh"}
        )
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "1//fake-refresh"
        mock_creds.to_json.return_value = refreshed_json
        mock_from_info.return_value = mock_creds

        result = load_credentials("/creds.json", str(token_path), manager=key_manager)

        assert result is mock_creds
        mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)
        # On-disk file is the encryption envelope, NOT plaintext refresh_token.
        on_disk = token_path.read_text(encoding="utf-8")
        assert "1//fake-refresh" not in on_disk
        assert json.loads(on_disk).get("ccas_enc") is not None
        assert mode_is_0600(token_path)

    @patch("ccas.ingestor.auth.Request")
    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_info")
    def test_refresh_failure_raises_gmail_auth_error(
        self, mock_from_info, mock_request_cls, tmp_path, key_manager
    ):
        """refresh 失敗時拋出 GmailAuthError，訊息包含重新授權指引。"""
        token_path = tmp_path / "token.json"
        write_encrypted_token_file(token_path, _TOKEN_JSON, key_manager)

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "1//fake-refresh"
        mock_creds.refresh.side_effect = RefreshError("token revoked")
        mock_from_info.return_value = mock_creds

        with pytest.raises(GmailAuthError, match="刷新失敗"):
            load_credentials("/creds.json", str(token_path), manager=key_manager)

    def test_token_not_found_raises_gmail_auth_error(self, key_manager):
        """token 檔案不存在時拋出 GmailAuthError。"""
        with pytest.raises(GmailAuthError, match="不存在"):
            load_credentials(
                "/creds.json", "/nonexistent/token.json", manager=key_manager
            )

    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_info")
    def test_invalid_token_no_refresh_token_raises_error(
        self, mock_from_info, tmp_path, key_manager
    ):
        """token 無效且沒有 refresh_token 時拋出 GmailAuthError。"""
        token_path = tmp_path / "token.json"
        write_encrypted_token_file(token_path, _TOKEN_JSON, key_manager)

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = None
        mock_from_info.return_value = mock_creds

        with pytest.raises(GmailAuthError, match="無法刷新"):
            load_credentials("/creds.json", str(token_path), manager=key_manager)


def mode_is_0600(path: Path) -> bool:
    """True when *path* has owner-only 0600 permission bits."""
    return stat.S_IMODE(path.stat().st_mode) == 0o600
