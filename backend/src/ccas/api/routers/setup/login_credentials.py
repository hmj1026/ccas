"""Bank login-credential management router (P3-7).

Encapsulates per-bank web-banking login credentials (e.g. FUBON's
``NATIONAL_ID`` / ``ROC_BIRTHDAY``). Plaintext values are encrypted with the
master.key Fernet (``MasterKeyManager``) before write; plaintext **never**
appears in any GET / PUT response.

Source precedence is mirrored in
``ccas.ingestor.credentials.resolve_bank_credential``:
``bank_login_credentials`` (DB) > env ``{BANK}_{KEY}`` > none. The DELETE
endpoint only removes the DB row, leaving env fallback intact (so operators
can transition gradually).

The credential universe is the explicit ``BANK_LOGIN_CREDENTIAL_KEYS``
registry — we never scan arbitrary ``{BANK}_{KEY}`` env vars (that would
misclassify unrelated keys like ``REDIS_URL`` as credentials).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankLoginCredentialStatus,
    BankLoginCredentialWriteRequest,
    BankLoginCredentialWriteResult,
    LoginCredentialImportResult,
)
from ccas.config import Settings, get_settings
from ccas.ingestor.credentials import known_credentials
from ccas.storage.database import get_db_session
from ccas.storage.models import BankLoginCredential

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/setup/login-credentials", tags=["setup-login-credentials"]
)


async def _db_credential_keys(session: AsyncSession) -> set[tuple[str, str]]:
    """所有已存在的 ``(bank_code, credential_key)`` DB row 鍵。"""
    rows = (
        await session.execute(
            select(
                BankLoginCredential.bank_code,
                BankLoginCredential.credential_key,
            )
        )
    ).all()
    return {(bank, key) for bank, key in rows}


@router.get("", response_model=ApiResponse[list[BankLoginCredentialStatus]])
async def list_login_credentials(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[list[BankLoginCredentialStatus]]:
    """List source state for every known login credential (no plaintext)。

    Universe = registry ``BANK_LOGIN_CREDENTIAL_KEYS`` ∪ DB rows。
    """
    db_keys = await _db_credential_keys(session)
    universe = set(known_credentials()) | db_keys

    items: list[BankLoginCredentialStatus] = []
    for bank_code, credential_key in sorted(universe):
        has_db = (bank_code, credential_key) in db_keys
        has_env = bool(settings.get_bank_credential(bank_code, credential_key))
        if has_db:
            source = "db"
        elif has_env:
            source = "env"
        else:
            source = "none"
        items.append(
            BankLoginCredentialStatus(
                bank_code=bank_code,
                credential_key=credential_key,
                has_db_value=has_db,
                has_env_value=has_env,
                effective_source=source,
            )
        )
    return ApiResponse(data=items)


@router.put(
    "/{bank_code}/{credential_key}",
    response_model=ApiResponse[BankLoginCredentialWriteResult],
)
async def upsert_login_credential(
    bank_code: str,
    credential_key: str,
    payload: BankLoginCredentialWriteRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[BankLoginCredentialWriteResult]:
    """Encrypt + UPSERT a single per-bank login credential."""
    bank = bank_code.strip().upper()
    key = credential_key.strip().upper()
    if not bank or not key:
        raise HTTPException(
            status_code=422, detail="bank_code 與 credential_key 不可為空"
        )
    # 只允許寫入註冊表已知的登入憑證，避免寫入永不會被 resolver 取用、
    # 僅汙染 GET 列表的孤兒列。
    if (bank, key) not in set(known_credentials()):
        raise HTTPException(
            status_code=422,
            detail=f"未知的登入憑證組合：{bank}/{key}",
        )

    cipher = settings.master_key_manager.encrypt(payload.value)
    # Race-safe UPSERT on the composite PK — see banks.py rationale.
    stmt = sqlite_insert(BankLoginCredential).values(
        bank_code=bank, credential_key=key, encrypted_value=cipher
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            BankLoginCredential.bank_code,
            BankLoginCredential.credential_key,
        ],
        set_={"encrypted_value": cipher},
    )
    await session.execute(stmt)
    await session.commit()
    return ApiResponse(
        data=BankLoginCredentialWriteResult(
            bank_code=bank,
            credential_key=key,
            effective_source="db",
        )
    )


@router.delete(
    "/{bank_code}/{credential_key}",
    response_model=ApiResponse[BankLoginCredentialWriteResult],
)
async def delete_login_credential(
    bank_code: str,
    credential_key: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[BankLoginCredentialWriteResult]:
    """Remove the DB-stored credential. Env fallback (if any) remains active."""
    bank = bank_code.strip().upper()
    key = credential_key.strip().upper()
    row = await session.get(BankLoginCredential, (bank, key))
    if row is not None:
        await session.delete(row)
        await session.commit()

    has_env = bool(settings.get_bank_credential(bank, key))
    return ApiResponse(
        data=BankLoginCredentialWriteResult(
            bank_code=bank,
            credential_key=key,
            effective_source="env" if has_env else "none",
        )
    )


@router.post(
    "/import-from-env",
    response_model=ApiResponse[LoginCredentialImportResult],
)
async def import_from_env(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[LoginCredentialImportResult]:
    """Bulk-encrypt every registry credential present only in env into DB rows.

    Counting note: a registry credential set in neither DB nor env is dropped
    silently (counted in neither ``imported`` nor ``skipped_already_in_db``),
    so the two counts may not sum to the registry size — that residual is the
    "not configured anywhere" set. (Matches setup/secrets.py import behaviour.)
    """
    db_keys = await _db_credential_keys(session)

    imported: list[str] = []
    skipped = 0
    for bank_code, credential_key in sorted(known_credentials()):
        if (bank_code, credential_key) in db_keys:
            skipped += 1
            continue
        plaintext = settings.get_bank_credential(bank_code, credential_key)
        if not plaintext:
            continue
        cipher = settings.master_key_manager.encrypt(plaintext)
        session.add(
            BankLoginCredential(
                bank_code=bank_code,
                credential_key=credential_key,
                encrypted_value=cipher,
            )
        )
        imported.append(f"{bank_code}_{credential_key}")
    if imported:
        await session.commit()
    logger.info(
        "login-credential import-from-env done",
        extra={"imported": len(imported), "skipped": skipped},
    )
    return ApiResponse(
        data=LoginCredentialImportResult(
            imported=len(imported),
            skipped_already_in_db=skipped,
            credentials_imported=imported,
        )
    )
