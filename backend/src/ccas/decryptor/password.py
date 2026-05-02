"""PDF 密碼解析模組。

優先序（oauth-onboarding-ui §5.6）：

1. ``bank_secrets`` DB row（以 ``MasterKeyManager`` Fernet 解密）
2. 環境變數 ``PDF_PASSWORD_{BANK_CODE}``（以及 legacy 一律走 env）
3. 無

當 DB row 存在但解密失敗時 raise ``DecryptError``，明確指出 master.key
與密文不匹配（避免被誤判為 PDF 密碼錯）。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import Settings
from ccas.errors import DecryptError
from ccas.storage.models import BankSecret
from ccas.storage.secrets import MasterKeyMismatchError


async def resolve_password(
    session: AsyncSession,
    settings: Settings,
    bank_code: str,
) -> str | None:
    """取得指定銀行的主 PDF 解密密碼。

    DB row 存在 → Fernet 解密回傳；無 row → 回傳 env 值；皆無 → ``None``。

    Raises:
        DecryptError: DB row 存在但 master.key 無法解密該密文時拋出，
            訊息明示「master.key 與密文不匹配」。
    """
    code = bank_code.upper()
    db_row = await session.get(BankSecret, code)
    if db_row is not None:
        try:
            return settings.master_key_manager.decrypt(db_row.encrypted_password)
        except MasterKeyMismatchError as exc:
            raise DecryptError(
                f"PDF 密碼解密失敗（{code}）",
                "master.key 與密文不匹配，請確認資料目錄完整還原",
                bank_code=code,
            ) from exc
    return settings.get_pdf_password(code)


async def resolve_passwords(
    session: AsyncSession,
    settings: Settings,
    bank_code: str,
) -> tuple[str, ...]:
    """取得指定銀行的所有候選 PDF 解密密碼。

    主密碼優先採用 DB row（若存在），其餘走 env；legacy 密碼一律從 env
    取得（DB 不儲存 legacy）。回傳 tuple 順序：主密碼 → legacy_1 ... _N。

    Raises:
        DecryptError: 主密碼 DB row 存在但 master.key 無法解密時拋出。
    """
    candidates: list[str] = []
    primary = await resolve_password(session, settings, bank_code)
    if primary:
        candidates.append(primary)
    env_chain = settings.get_pdf_passwords(bank_code)
    # 主密碼可能來自 DB；legacy 與「env 主密碼（若 DB 沒有 → 已含於 primary）」
    # 都從 env_chain 補：跳過已加入的主密碼，避免重複。
    for value in env_chain:
        if value and value not in candidates:
            candidates.append(value)
    return tuple(candidates)
