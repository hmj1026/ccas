"""PDF 解密核心邏輯的單元測試。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ccas.decryptor.decrypt import DecryptionError, DecryptResult, decrypt_pdf


class TestDecryptPdfUnencrypted:
    """未加密 PDF 透通的測試案例。"""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_unencrypted_pdf_passthrough(self, mock_pikepdf):
        """未加密 PDF 直接透通，不拋出例外。"""
        mock_pdf = MagicMock()
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        result = decrypt_pdf(Path("/fake/bill.pdf"), password=None)

        assert result == DecryptResult(needed_decryption=False)
        mock_pdf.save.assert_called_once_with(Path("/fake/bill.pdf"))

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_unencrypted_pdf_with_password_still_passthrough(self, mock_pikepdf):
        """未加密 PDF 即使提供密碼也直接透通。"""
        mock_pdf = MagicMock()
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        result = decrypt_pdf(Path("/fake/bill.pdf"), password="unused")

        assert result == DecryptResult(needed_decryption=False)


class TestDecryptPdfEncrypted:
    """加密 PDF 解密的測試案例。"""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_correct_password(self, mock_pikepdf):
        """以正確密碼成功解密加密 PDF。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})

        # First open (no password) raises PasswordError
        # Second open (with password) succeeds
        mock_pdf = MagicMock()
        call_count = {"n": 0}

        def fake_open(path, password=None, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise mock_pikepdf.PasswordError("encrypted")
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=mock_pdf)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_pikepdf.open.side_effect = fake_open

        result = decrypt_pdf(Path("/fake/encrypted.pdf"), password="correct")

        assert result == DecryptResult(needed_decryption=True)
        mock_pdf.save.assert_called_once_with(Path("/fake/encrypted.pdf"))

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_wrong_password(self, mock_pikepdf):
        """以錯誤密碼解密失敗，拋出 DecryptionError。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("bad password")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match="Invalid password"):
            decrypt_pdf(Path("/fake/encrypted.pdf"), password="wrong")

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_no_password(self, mock_pikepdf):
        """加密 PDF 無密碼可用時拋出 DecryptionError。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("encrypted")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match="Password not found in settings"):
            decrypt_pdf(Path("/fake/encrypted.pdf"), password=None)
