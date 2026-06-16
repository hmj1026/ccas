"""At-rest encryption for Gmail OAuth credential files.

``token.json`` and ``credentials.json`` hold long-lived secrets (a Google
``refresh_token`` and the OAuth ``client_secret``). Historically they were
written as plaintext JSON on disk, protected only by ``0600`` perms and
``.gitignore``. This module encrypts them at rest with the **same**
``MasterKeyManager`` Fernet used for ``BankSecret`` PDF passwords, so a leaked
``data/`` snapshot (without ``master.key``) no longer exposes the tokens.

Format
------
An encrypted file is a small JSON envelope::

    {"ccas_enc": 1, "ciphertext": "<fernet-token>"}

The envelope (rather than a bare Fernet token) keeps the file valid JSON and
gives a cheap, unambiguous discriminator for the read path.

Legacy tolerance
----------------
``read_token_file`` first tries to parse-and-decrypt the envelope. If the file
is a *legacy plaintext* JSON object (no ``ccas_enc`` marker), it is returned
as-is so existing deployments keep working; the next write re-encrypts it.
This is why callers should route refresh write-backs through
``write_encrypted_token_file`` — otherwise a refresh would silently rewrite the
file as plaintext again.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ccas.storage.atomic import atomic_write_bytes
from ccas.storage.secrets import MasterKeyMismatchError

if TYPE_CHECKING:
    from ccas.storage.secrets import MasterKeyManager

logger = logging.getLogger(__name__)

# Envelope marker key + current schema version. Bump ``_ENC_VERSION`` only on a
# breaking envelope change (the reader checks presence of the key, not value).
_ENC_MARKER = "ccas_enc"
_ENC_VERSION = 1
_CIPHERTEXT_KEY = "ciphertext"
_FILE_MODE = 0o600


def _looks_encrypted(payload: object) -> bool:
    """Return True when *payload* is a CCAS encryption envelope dict.

    Matches on the exact ``_ENC_VERSION`` (not merely "marker present"): this
    rejects ``{"ccas_enc": null}`` / ``{"ccas_enc": 0}`` edge cases as legacy
    plaintext rather than feeding garbage to ``decrypt`` (security-reviewer H3),
    and a future v2 envelope read by a v1 reader cleanly falls through instead of
    silently mis-decrypting.
    """
    return (
        isinstance(payload, dict)
        and payload.get(_ENC_MARKER) == _ENC_VERSION
        and isinstance(payload.get(_CIPHERTEXT_KEY), str)
    )


def write_encrypted_token_file(
    path: Path, content: str, manager: MasterKeyManager
) -> None:
    """Encrypt *content* with the master key and write it atomically (0600).

    *content* is the plaintext JSON string the caller wants persisted (e.g.
    ``json.dumps(token_record)`` or ``creds.to_json()``). It is wrapped in the
    encryption envelope and written via :func:`atomic_write_bytes` so a crash
    or concurrent reader never observes a partial file.

    Args:
        path: Destination file (``token.json`` / ``credentials.json``).
        content: Plaintext JSON payload to encrypt.
        manager: Shared ``MasterKeyManager`` (Fernet) instance.
    """
    ciphertext = manager.encrypt(content)
    envelope = json.dumps({_ENC_MARKER: _ENC_VERSION, _CIPHERTEXT_KEY: ciphertext})
    atomic_write_bytes(path, envelope.encode("utf-8"), mode=_FILE_MODE)


def read_token_file(path: Path, manager: MasterKeyManager) -> str:
    """Read an OAuth credential file, decrypting when encrypted.

    Tolerates legacy plaintext files: if the on-disk JSON lacks the encryption
    envelope, its raw text is returned unchanged so pre-existing deployments
    keep loading. Encrypted files are decrypted and the inner plaintext JSON
    string is returned.

    Args:
        path: File to read.
        manager: Shared ``MasterKeyManager`` used to decrypt.

    Returns:
        The plaintext JSON content as a string.

    Raises:
        FileNotFoundError: *path* does not exist.
        MasterKeyMismatchError: file is encrypted but the current master.key
            cannot decrypt it (propagated from ``MasterKeyManager.decrypt`` so
            operators get the "restore data/secrets" guidance — never silently
            falls back to plaintext on a decrypt failure of *encrypted* data).
    """
    raw = path.read_text(encoding="utf-8")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        # Not JSON at all — hand the raw bytes back; callers' own JSON parse
        # surfaces a precise error in their context.
        return raw
    if _looks_encrypted(payload):
        return manager.decrypt(payload[_CIPHERTEXT_KEY])
    # Legacy plaintext JSON object: return verbatim. The next write through
    # ``write_encrypted_token_file`` upgrades it to the encrypted envelope.
    return raw


def read_token_payload(path: Path, manager: MasterKeyManager) -> dict[str, Any]:
    """Read and JSON-parse an OAuth credential file into a dict.

    Convenience wrapper over :func:`read_token_file` for the common case where
    the caller wants the parsed object (``google-auth``'s
    ``from_authorized_user_info`` and the gmail router's status/revoke paths).

    Raises:
        FileNotFoundError: *path* does not exist.
        json.JSONDecodeError: decrypted/plaintext content is not valid JSON.
        MasterKeyMismatchError: encrypted file cannot be decrypted.
    """
    plaintext = read_token_file(path, manager)
    data = json.loads(plaintext)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("expected JSON object", plaintext, 0)
    return data


__all__ = [
    "MasterKeyMismatchError",
    "read_token_file",
    "read_token_payload",
    "write_encrypted_token_file",
]
