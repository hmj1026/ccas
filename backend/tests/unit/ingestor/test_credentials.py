"""``ccas.ingestor.credentials`` 的單元測試。

涵蓋 ``known_credentials()`` 列舉與 ``resolve_bank_credential()`` 的三條
優先序分支（DB row 解密 / env fallback / None），以及 master.key 不匹配時
轉拋 ``IngestError`` 的行為。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ccas.errors import IngestError
from ccas.ingestor.credentials import known_credentials, resolve_bank_credential
from ccas.storage.secrets import MasterKeyMismatchError


def test_known_credentials_returns_fubon_pairs() -> None:
    """列舉所有 ``(bank_code, credential_key)`` 組合（皆大寫）。"""
    pairs = known_credentials()
    assert ("FUBON", "NATIONAL_ID") in pairs
    assert ("FUBON", "ROC_BIRTHDAY") in pairs
    # 每個元素皆為大寫的二元組。
    for bank_code, key in pairs:
        assert bank_code == bank_code.upper()
        assert key == key.upper()


async def test_db_row_decrypts_and_returns() -> None:
    """DB row 存在時以 master_key_manager 解密並回傳。"""
    db_row = MagicMock(encrypted_value=b"cipher")
    session = AsyncMock()
    session.get.return_value = db_row

    settings = MagicMock()
    settings.master_key_manager.decrypt.return_value = "A123456789"

    result = await resolve_bank_credential(session, settings, "FUBON", "NATIONAL_ID")

    assert result == "A123456789"
    settings.master_key_manager.decrypt.assert_called_once_with(b"cipher")
    # env fallback 不應被觸碰。
    settings.get_bank_credential.assert_not_called()


async def test_db_row_decrypt_failure_raises_ingest_error() -> None:
    """master.key 不匹配時轉拋 ``IngestError`` 並帶入 bank_code。"""
    db_row = MagicMock(encrypted_value=b"cipher")
    session = AsyncMock()
    session.get.return_value = db_row

    settings = MagicMock()
    settings.master_key_manager.decrypt.side_effect = MasterKeyMismatchError("boom")

    with pytest.raises(IngestError) as exc_info:
        await resolve_bank_credential(session, settings, "fubon", "national_id")

    assert "master.key" in str(exc_info.value)
    assert exc_info.value.context["bank_code"] == "FUBON"
    # 原始例外應被鏈結（raise ... from exc）。
    assert isinstance(exc_info.value.__cause__, MasterKeyMismatchError)


async def test_no_db_row_returns_env_value() -> None:
    """無 DB row 時回退到環境變數值。"""
    session = AsyncMock()
    session.get.return_value = None

    settings = MagicMock()
    settings.get_bank_credential.return_value = "env-secret"

    result = await resolve_bank_credential(session, settings, "FUBON", "NATIONAL_ID")

    assert result == "env-secret"
    settings.get_bank_credential.assert_called_once_with("FUBON", "NATIONAL_ID")


async def test_no_db_row_empty_env_returns_none() -> None:
    """env 值為空字串時視為「無」，回傳 None。"""
    session = AsyncMock()
    session.get.return_value = None

    settings = MagicMock()
    settings.get_bank_credential.return_value = ""

    result = await resolve_bank_credential(session, settings, "FUBON", "ROC_BIRTHDAY")

    assert result is None


async def test_lookup_key_is_normalized_to_upper() -> None:
    """bank_code 與 key 皆轉大寫後才查 DB。"""
    session = AsyncMock()
    session.get.return_value = None

    settings = MagicMock()
    settings.get_bank_credential.return_value = None

    await resolve_bank_credential(session, settings, "fubon", "national_id")

    # session.get 的複合主鍵應為大寫元組。
    _, key_tuple = session.get.call_args.args
    assert key_tuple == ("FUBON", "NATIONAL_ID")
