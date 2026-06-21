"""銀行網銀登入憑證解析（P3-7）。

優先序（鏡像 ``ccas.decryptor.password.resolve_password``）：

1. ``bank_login_credentials`` DB row（以 ``MasterKeyManager`` Fernet 解密）
2. 環境變數 ``{BANK_CODE}_{KEY}``（legacy fallback）
3. 無 → ``None``

當 DB row 存在但解密失敗時 raise ``IngestError``，明確指出 master.key
與密文不匹配（避免被誤判為憑證錯誤）。

``BANK_LOGIN_CREDENTIAL_KEYS`` 是「哪些 ``{BANK}_{KEY}`` 屬於登入憑證」的
唯一真實來源：env 掃描與 setup UI 皆據此列舉，**不**做任意前綴掃描
（否則會誤把 ``REDIS_URL`` 等無關 env 視為憑證）。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import Settings
from ccas.errors import IngestError
from ccas.storage.models import BankLoginCredential
from ccas.storage.secrets import MasterKeyMismatchError

# 已知的銀行登入憑證鍵名（bank_code → 該行所需的 credential_key 集合）。
# 新增需要網銀登入的 parser 時，於此登錄其憑證鍵名。
BANK_LOGIN_CREDENTIAL_KEYS: dict[str, tuple[str, ...]] = {
    "FUBON": ("NATIONAL_ID", "ROC_BIRTHDAY"),
}


def known_credentials() -> list[tuple[str, str]]:
    """列舉所有已知的 ``(bank_code, credential_key)`` 組合（皆大寫）。"""
    return [
        (bank_code, key)
        for bank_code, keys in BANK_LOGIN_CREDENTIAL_KEYS.items()
        for key in keys
    ]


async def resolve_bank_credential(
    session: AsyncSession,
    settings: Settings,
    bank_code: str,
    key: str,
) -> str | None:
    """取得指定銀行的單一登入憑證值。

    DB row 存在 → Fernet 解密回傳；無 row → 回傳 env 值；皆無 → ``None``。

    Raises:
        IngestError: DB row 存在但 master.key 無法解密該密文時拋出，
            訊息明示「master.key 與密文不匹配」。
    """
    code = bank_code.upper()
    cred_key = key.upper()
    db_row = await session.get(BankLoginCredential, (code, cred_key))
    if db_row is not None:
        try:
            return settings.master_key_manager.decrypt(db_row.encrypted_value)
        except MasterKeyMismatchError as exc:
            raise IngestError(
                f"登入憑證解密失敗（{code}/{cred_key}）",
                "master.key 與密文不匹配，請確認資料目錄完整還原",
                bank_code=code,
            ) from exc
    # 空字串 env 值（或未設定）一律視為「無」，符合 None 契約。
    return settings.get_bank_credential(code, cred_key) or None
