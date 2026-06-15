"""PDF 解密核心邏輯的單元測試。

解密採 temp-then-rename 原子覆寫：來源以唯讀開啟，解密結果先寫入同目錄的
``.dec.tmp`` 暫存檔，成功後才 ``os.replace`` 換入。測試以 ``tmp_path``
建立真實目錄，並驗證暫存檔不殘留。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pikepdf
import pytest

from ccas.decryptor.decrypt import DecryptionError, DecryptResult, decrypt_pdf


def _no_dec_tmp_residue(directory: Path) -> bool:
    """確認目錄下沒有殘留的 .dec.tmp 暫存檔。"""
    return not any(directory.glob("*.dec.tmp"))


class TestDecryptPdfUnencrypted:
    """未加密 PDF 透通的測試案例。"""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_unencrypted_pdf_passthrough(self, mock_pikepdf, tmp_path: Path):
        """未加密 PDF 直接透通，不拋出例外，且不殘留暫存檔。"""
        mock_pikepdf.PasswordError = pikepdf.PasswordError
        pdf_path = tmp_path / "bill.pdf"
        pdf_path.write_bytes(b"original")

        mock_pdf = MagicMock()
        mock_pdf.save.side_effect = lambda tmp: Path(tmp).write_bytes(b"decrypted")
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        result = decrypt_pdf(pdf_path, password=None)

        assert result == DecryptResult(needed_decryption=False)
        # save() is invoked against the temp path, not the original in place.
        save_arg = Path(mock_pdf.save.call_args.args[0])
        assert save_arg != pdf_path
        assert save_arg.parent == pdf_path.parent
        assert pdf_path.read_bytes() == b"decrypted"
        assert _no_dec_tmp_residue(tmp_path)

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_unencrypted_pdf_with_password_still_passthrough(
        self, mock_pikepdf, tmp_path: Path
    ):
        """未加密 PDF 即使提供密碼也直接透通。"""
        mock_pikepdf.PasswordError = pikepdf.PasswordError
        pdf_path = tmp_path / "bill.pdf"
        pdf_path.write_bytes(b"original")

        mock_pdf = MagicMock()
        mock_pdf.save.side_effect = lambda tmp: Path(tmp).write_bytes(b"x")
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        result = decrypt_pdf(pdf_path, password="unused")

        assert result == DecryptResult(needed_decryption=False)
        assert _no_dec_tmp_residue(tmp_path)


class TestDecryptPdfEncrypted:
    """加密 PDF 解密的測試案例。"""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_correct_password(self, mock_pikepdf, tmp_path: Path):
        """以正確密碼成功解密加密 PDF（原子覆寫，無暫存殘留）。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        pdf_path = tmp_path / "encrypted.pdf"
        pdf_path.write_bytes(b"original")

        # First open (no password) raises PasswordError
        # Second open (with password) succeeds
        mock_pdf = MagicMock()
        mock_pdf.save.side_effect = lambda tmp: Path(tmp).write_bytes(b"decrypted")
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

        result = decrypt_pdf(pdf_path, password="correct")

        assert result == DecryptResult(needed_decryption=True)
        save_arg = Path(mock_pdf.save.call_args.args[0])
        assert save_arg != pdf_path
        assert pdf_path.read_bytes() == b"decrypted"
        assert _no_dec_tmp_residue(tmp_path)

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_wrong_password(self, mock_pikepdf, tmp_path: Path):
        """以錯誤密碼解密失敗，拋出 DecryptionError。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        pdf_path = tmp_path / "encrypted.pdf"
        pdf_path.write_bytes(b"original")

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("bad password")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match="Invalid password"):
            decrypt_pdf(pdf_path, password="wrong")
        assert _no_dec_tmp_residue(tmp_path)

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_encrypted_pdf_no_password(self, mock_pikepdf, tmp_path: Path):
        """加密 PDF 無密碼可用時拋出 DecryptionError。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        pdf_path = tmp_path / "encrypted.pdf"
        pdf_path.write_bytes(b"original")

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("encrypted")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match="Password not found in settings"):
            decrypt_pdf(pdf_path, password=None)
        assert _no_dec_tmp_residue(tmp_path)


class TestDecryptPdfSaveFailureIsAtomic:
    """save() I/O 失敗時例外傳播且不損毀原檔、不殘留暫存檔。"""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_save_oserror_propagates_and_no_residue(self, mock_pikepdf, tmp_path: Path):
        """save() 拋 OSError 時，例外向上傳播（未被吞掉），原檔保留、無暫存殘留。"""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        pdf_path = tmp_path / "bill.pdf"
        pdf_path.write_bytes(b"original-bytes")

        mock_pdf = MagicMock()

        def boom_save(tmp_target):
            # Simulate a mid-save crash: partial write to the temp file, then fail.
            Path(tmp_target).write_bytes(b"partial")
            raise OSError("disk full")

        mock_pdf.save.side_effect = boom_save
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(OSError, match="disk full"):
            decrypt_pdf(pdf_path, password=None)

        # The exception must NOT be silently swallowed (asserted by pytest.raises),
        # the original PDF must be intact, and no .dec.tmp residue may remain.
        assert pdf_path.read_bytes() == b"original-bytes"
        assert _no_dec_tmp_residue(tmp_path)
