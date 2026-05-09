"""Multi-password fallback decryption tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ccas.decryptor.decrypt import DecryptionError, DecryptResult, decrypt_pdf_multi


class TestDecryptPdfMultiUnencrypted:
    """Unencrypted PDF passthrough with multi-password API."""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_unencrypted_passthrough(self, mock_pikepdf):
        """Unencrypted PDF passes through regardless of passwords."""
        mock_pdf = MagicMock()
        mock_pikepdf.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pikepdf.open.return_value.__exit__ = MagicMock(return_value=False)

        result = decrypt_pdf_multi(Path("/fake/bill.pdf"), ("pw1", "pw2"))

        assert result == DecryptResult(needed_decryption=False)


class TestDecryptPdfMultiFallback:
    """Multi-password fallback behavior."""

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_primary_succeeds_legacy_not_tried(self, mock_pikepdf):
        """Primary password works -> legacy never attempted."""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        call_count = {"n": 0}

        def fake_open(path, password=None, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise mock_pikepdf.PasswordError("encrypted")
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=MagicMock())
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_pikepdf.open.side_effect = fake_open

        result = decrypt_pdf_multi(
            Path("/fake/encrypted.pdf"), ("correct-pw", "legacy-pw")
        )

        assert result == DecryptResult(needed_decryption=True)
        assert call_count["n"] == 2  # no-password attempt + primary
        passwords_used = [
            c.kwargs.get("password") for c in mock_pikepdf.open.call_args_list
        ]
        assert "legacy-pw" not in passwords_used

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_primary_fails_legacy_succeeds(self, mock_pikepdf):
        """Primary fails, legacy_1 succeeds -> decrypted."""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})
        call_count = {"n": 0}

        def fake_open(path, password=None, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:  # no-password + primary both fail
                raise mock_pikepdf.PasswordError("bad")
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=MagicMock())
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_pikepdf.open.side_effect = fake_open

        result = decrypt_pdf_multi(
            Path("/fake/encrypted.pdf"), ("wrong-pw", "correct-legacy")
        )

        assert result == DecryptResult(needed_decryption=True)
        assert call_count["n"] == 3  # no-password + primary + legacy

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_all_candidates_fail(self, mock_pikepdf):
        """All passwords fail -> error with candidate count."""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("bad")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match=r"tried 3 candidates"):
            decrypt_pdf_multi(Path("/fake/encrypted.pdf"), ("pw1", "pw2", "pw3"))

    @patch("ccas.decryptor.decrypt.pikepdf")
    def test_empty_tuple_no_password(self, mock_pikepdf):
        """Empty password tuple -> 'Password not found in settings'."""
        mock_pikepdf.PasswordError = type("PasswordError", (Exception,), {})

        def fake_open(path, password=None, **kwargs):
            raise mock_pikepdf.PasswordError("encrypted")

        mock_pikepdf.open.side_effect = fake_open

        with pytest.raises(DecryptionError, match="Password not found in settings"):
            decrypt_pdf_multi(Path("/fake/encrypted.pdf"), ())
