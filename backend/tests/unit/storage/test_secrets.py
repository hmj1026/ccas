"""Tests for MasterKeyManager (Fernet 對稱加密)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from ccas.storage.secrets import MasterKeyManager, MasterKeyMismatchError

_FERNET_KEY_LEN = 44  # base64 url-safe encoded 32-byte key


class TestLoadOrCreate:
    def test_first_call_generates_key_with_0600_perm(self, tmp_path: Path) -> None:
        key_path = tmp_path / "secrets" / "master.key"
        mgr = MasterKeyManager(key_path)

        key = mgr.load_or_create()

        assert key_path.exists()
        assert len(key) == _FERNET_KEY_LEN
        # Permission must be 0600 (owner-only read/write).
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_existing_key_is_not_overwritten(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key"
        existing = Fernet.generate_key()
        key_path.write_bytes(existing)
        os.chmod(key_path, 0o600)

        mgr = MasterKeyManager(key_path)
        loaded = mgr.load_or_create()

        assert loaded == existing

    def test_load_or_create_is_idempotent(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key"
        mgr = MasterKeyManager(key_path)

        first = mgr.load_or_create()
        second = mgr.load_or_create()

        assert first == second


class TestEncryptDecrypt:
    def test_encrypt_then_decrypt_roundtrip_ascii(self, tmp_path: Path) -> None:
        mgr = MasterKeyManager(tmp_path / "master.key")
        plaintext = "my-pdf-password-12345"

        ct = mgr.encrypt(plaintext)
        recovered = mgr.decrypt(ct)

        assert recovered == plaintext
        assert ct != plaintext  # never store plaintext

    def test_encrypt_then_decrypt_roundtrip_unicode(self, tmp_path: Path) -> None:
        mgr = MasterKeyManager(tmp_path / "master.key")
        plaintext = "中文密碼-emoji-🔐"

        ct = mgr.encrypt(plaintext)

        assert mgr.decrypt(ct) == plaintext

    def test_decrypt_with_different_key_raises_mismatch(self, tmp_path: Path) -> None:
        mgr_a = MasterKeyManager(tmp_path / "a" / "master.key")
        mgr_b = MasterKeyManager(tmp_path / "b" / "master.key")
        ct_from_a = mgr_a.encrypt("secret")

        with pytest.raises(MasterKeyMismatchError) as exc_info:
            mgr_b.decrypt(ct_from_a)

        # Error message MUST mention master.key so operators can act on it.
        assert "master.key" in str(exc_info.value).lower()

    def test_get_fernet_returns_cached_instance(self, tmp_path: Path) -> None:
        mgr = MasterKeyManager(tmp_path / "master.key")

        f1 = mgr.get_fernet()
        f2 = mgr.get_fernet()

        assert f1 is f2  # lazy cache
        assert isinstance(f1, Fernet)
