"""OAuth 憑證載入與 token 自動刷新的單元測試。"""

from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from ccas.ingestor.auth import GmailAuthError, load_credentials


class TestLoadCredentials:
    """load_credentials() 的測試案例。"""

    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_file")
    @patch("ccas.ingestor.auth.Path")
    def test_valid_token_returns_credentials(self, mock_path_cls, mock_from_file):
        """token 有效時直接回傳 credentials，不呼叫 refresh。"""
        mock_path_cls.return_value.exists.return_value = True
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_from_file.return_value = mock_creds

        result = load_credentials("/creds.json", "/token.json")

        assert result is mock_creds
        mock_creds.refresh.assert_not_called()

    @patch("ccas.ingestor.auth.Request")
    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_file")
    @patch("ccas.ingestor.auth.Path")
    def test_expired_token_auto_refreshes(
        self, mock_path_cls, mock_from_file, mock_request_cls
    ):
        """token 過期時自動呼叫 refresh()。"""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_cls.return_value = mock_path_instance

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token-value"
        mock_creds.to_json.return_value = '{"token": "refreshed"}'
        mock_from_file.return_value = mock_creds

        result = load_credentials("/creds.json", "/token.json")

        assert result is mock_creds
        mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)

    @patch("ccas.ingestor.auth.Request")
    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_file")
    @patch("ccas.ingestor.auth.Path")
    def test_refresh_failure_raises_gmail_auth_error(
        self, mock_path_cls, mock_from_file, mock_request_cls
    ):
        """refresh 失敗時拋出 GmailAuthError，訊息包含重新授權指引。"""
        mock_path_cls.return_value.exists.return_value = True

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token-value"
        mock_creds.refresh.side_effect = RefreshError("token revoked")
        mock_from_file.return_value = mock_creds

        with pytest.raises(GmailAuthError, match="刷新失敗"):
            load_credentials("/creds.json", "/token.json")

    @patch("ccas.ingestor.auth.Path")
    def test_token_not_found_raises_gmail_auth_error(self, mock_path_cls):
        """token 檔案不存在時拋出 GmailAuthError。"""
        mock_path_cls.return_value.exists.return_value = False

        with pytest.raises(GmailAuthError, match="不存在"):
            load_credentials("/creds.json", "/nonexistent/token.json")

    @patch("ccas.ingestor.auth.Credentials.from_authorized_user_file")
    @patch("ccas.ingestor.auth.Path")
    def test_invalid_token_no_refresh_token_raises_error(
        self, mock_path_cls, mock_from_file
    ):
        """token 無效且沒有 refresh_token 時拋出 GmailAuthError。"""
        mock_path_cls.return_value.exists.return_value = True

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = None
        mock_from_file.return_value = mock_creds

        with pytest.raises(GmailAuthError, match="無法刷新"):
            load_credentials("/creds.json", "/token.json")
