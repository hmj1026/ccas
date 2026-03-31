"""密碼解析與產生的單元測試。"""

import os
from unittest.mock import MagicMock

from ccas.decryptor.password import resolve_password


class TestResolvePassword:
    """resolve_password() 的測試案例。"""

    def test_returns_password_from_env(self, monkeypatch):
        """環境變數有設定時回傳密碼。"""
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "secret123")
        settings = MagicMock()
        settings.get_pdf_password.side_effect = (
            lambda code: os.environ.get(f"PDF_PASSWORD_{code.upper()}")
        )

        result = resolve_password(settings, "CTBC")
        assert result == "secret123"

    def test_returns_none_when_not_set(self):
        """環境變數未設定時回傳 None。"""
        settings = MagicMock()
        settings.get_pdf_password.return_value = None

        result = resolve_password(settings, "UNKNOWN_BANK")
        assert result is None

    def test_case_insensitive_bank_code(self, monkeypatch):
        """銀行代碼不分大小寫。"""
        monkeypatch.setenv("PDF_PASSWORD_CATHAY", "mypass")
        settings = MagicMock()
        settings.get_pdf_password.side_effect = (
            lambda code: os.environ.get(f"PDF_PASSWORD_{code.upper()}")
        )

        result = resolve_password(settings, "cathay")
        assert result == "mypass"

    def test_delegates_to_settings(self):
        """確認透過 settings.get_pdf_password() 查詢。"""
        settings = MagicMock()
        settings.get_pdf_password.return_value = "pw"

        resolve_password(settings, "CTBC")
        settings.get_pdf_password.assert_called_once_with("CTBC")
