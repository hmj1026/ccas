"""Unit tests for at-rest encryption of OAuth credential files (Stage 6 A3)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from ccas.storage.oauth_secrets import (
    read_token_file,
    read_token_payload,
    write_encrypted_token_file,
)
from ccas.storage.secrets import MasterKeyManager, MasterKeyMismatchError

_SECRET = "1//super-secret-refresh-token"
_PAYLOAD = {
    "token": "ya29.access",
    "refresh_token": _SECRET,
    "client_secret": "GOCSPX-confidential",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}


@pytest.fixture
def manager(tmp_path: Path) -> MasterKeyManager:
    return MasterKeyManager(tmp_path / "secrets" / "master.key")


def test_encrypted_file_is_not_plaintext(
    tmp_path: Path, manager: MasterKeyManager
) -> None:
    """On-disk file must not expose the secret in cleartext."""
    path = tmp_path / "token.json"
    write_encrypted_token_file(path, json.dumps(_PAYLOAD), manager)

    raw = path.read_text(encoding="utf-8")
    assert _SECRET not in raw
    assert "GOCSPX-confidential" not in raw
    # It is still valid JSON, but only the envelope — the inner object is hidden.
    envelope = json.loads(raw)
    assert envelope["ccas_enc"] == 1
    assert "ciphertext" in envelope
    assert "refresh_token" not in envelope


def test_encrypted_file_is_0600(tmp_path: Path, manager: MasterKeyManager) -> None:
    path = tmp_path / "token.json"
    write_encrypted_token_file(path, json.dumps(_PAYLOAD), manager)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_round_trip_via_read_path(tmp_path: Path, manager: MasterKeyManager) -> None:
    path = tmp_path / "token.json"
    write_encrypted_token_file(path, json.dumps(_PAYLOAD), manager)

    assert json.loads(read_token_file(path, manager)) == _PAYLOAD
    assert read_token_payload(path, manager) == _PAYLOAD


def test_legacy_plaintext_is_still_readable(
    tmp_path: Path, manager: MasterKeyManager
) -> None:
    """A pre-existing plaintext token.json (no envelope) loads unchanged."""
    path = tmp_path / "token.json"
    path.write_text(json.dumps(_PAYLOAD), encoding="utf-8")

    assert read_token_payload(path, manager) == _PAYLOAD


def test_wrong_master_key_fails_loud(tmp_path: Path) -> None:
    """An encrypted file written with one key cannot be silently read by another."""
    path = tmp_path / "token.json"
    writer = MasterKeyManager(tmp_path / "a" / "master.key")
    write_encrypted_token_file(path, json.dumps(_PAYLOAD), writer)

    other = MasterKeyManager(tmp_path / "b" / "master.key")
    with pytest.raises(MasterKeyMismatchError):
        read_token_payload(path, other)


def test_missing_file_raises(tmp_path: Path, manager: MasterKeyManager) -> None:
    with pytest.raises(FileNotFoundError):
        read_token_file(tmp_path / "absent.json", manager)


def test_non_object_payload_rejected(tmp_path: Path, manager: MasterKeyManager) -> None:
    """read_token_payload requires a JSON object (decrypted or legacy)."""
    path = tmp_path / "token.json"
    write_encrypted_token_file(path, json.dumps([1, 2, 3]), manager)
    with pytest.raises(json.JSONDecodeError):
        read_token_payload(path, manager)
