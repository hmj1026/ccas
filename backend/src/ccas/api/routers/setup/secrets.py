"""PDF secrets management router (oauth-onboarding-ui §5).

Encapsulates per-bank PDF decrypt password storage. Plaintext passwords are
encrypted with the master.key Fernet (``MasterKeyManager``) before write;
plaintext **never** appears in any GET / PUT response.

Source precedence is mirrored in ``ccas.decryptor.password.resolve_password``:
``bank_secrets`` (DB) > env ``PDF_PASSWORD_<CODE>`` > none. The DELETE
endpoint only removes the DB row, leaving env fallback intact (so operators
can transition gradually).

Import-from-env scans the merged env-map for ``PDF_PASSWORD_<CODE>`` keys
(excluding ``_LEGACY_*``) and writes any code that does not yet have a DB
row. Idempotent.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankSecretStatus,
    BankSecretWriteRequest,
    BankSecretWriteResult,
    ImportFromEnvResult,
)
from ccas.config import Settings, get_settings
from ccas.storage.database import get_db_session
from ccas.storage.models import BankConfig, BankSecret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup/secrets", tags=["setup-secrets"])

_PDF_PASSWORD_KEY = re.compile(r"^PDF_PASSWORD_([A-Z][A-Z0-9_]*?)$")

# Bank-code whitelist (mirrors storage.paths._BANK_CODE_RE). The path param is
# attacker-controllable by any valid-token holder; without this an arbitrary
# Unicode / whitespace / control string could be written into BankSecret.bank_code
# (String(32) PK), breaking downstream key comparison silently.
_BANK_CODE_RE = re.compile(r"^[A-Z0-9_-]+$")


def _normalize_bank_code(code: str) -> str:
    """Normalize + validate a bank-code path param, or raise HTTP 422."""
    normalized = code.strip().upper()
    if not _BANK_CODE_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail="bank code 格式無效，僅允許 A-Z、0-9、_、-",
        )
    return normalized


def _scan_env_codes(settings: Settings) -> set[str]:
    """Collect bank codes that have a ``PDF_PASSWORD_<CODE>`` env entry.

    ``_LEGACY_<n>`` suffixes are excluded by the regex (the trailing
    ``[A-Z0-9_]*?`` is anchored with ``$`` and we then filter out anything
    ending with ``_LEGACY_<digit>``).
    """
    codes: set[str] = set()
    for key, value in settings._env_map.items():  # noqa: SLF001
        if not value:
            continue
        match = _PDF_PASSWORD_KEY.match(key)
        if not match:
            continue
        code = match.group(1)
        if re.search(r"_LEGACY_\d+$", code):
            continue
        codes.add(code)
    return codes


@router.get("", response_model=ApiResponse[list[BankSecretStatus]])
async def list_secret_status(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[list[BankSecretStatus]]:
    """List secret-source state for every bank we know about.

    Bank universe = configs ∪ DB secret rows ∪ env-mentioned codes.
    Response **never** contains plaintext or ciphertext.
    """
    config_codes = {
        c for (c,) in (await session.execute(select(BankConfig.bank_code))).all()
    }
    secret_codes = {
        c for (c,) in (await session.execute(select(BankSecret.bank_code))).all()
    }
    env_codes = _scan_env_codes(settings)
    universe = config_codes | secret_codes | env_codes

    items: list[BankSecretStatus] = []
    for code in sorted(universe):
        has_db = code in secret_codes
        has_env = code in env_codes
        if has_db:
            source = "db"
        elif has_env:
            source = "env"
        else:
            source = "none"
        items.append(
            BankSecretStatus(
                bank_code=code,
                has_db_secret=has_db,
                has_env_secret=has_env,
                effective_source=source,
            )
        )
    return ApiResponse(data=items)


@router.put("/{code}", response_model=ApiResponse[BankSecretWriteResult])
async def upsert_secret(
    code: str,
    payload: BankSecretWriteRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[BankSecretWriteResult]:
    """Encrypt + UPSERT a per-bank PDF password."""
    normalized = _normalize_bank_code(code)

    cipher = settings.master_key_manager.encrypt(payload.password)
    # Race-safe UPSERT — see banks.py rationale.
    stmt = sqlite_insert(BankSecret).values(
        bank_code=normalized, encrypted_password=cipher
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[BankSecret.bank_code],
        set_={"encrypted_password": cipher},
    )
    await session.execute(stmt)
    await session.commit()
    return ApiResponse(
        data=BankSecretWriteResult(
            bank_code=normalized,
            effective_source="db",
        )
    )


@router.delete("/{code}", response_model=ApiResponse[BankSecretWriteResult])
async def delete_secret(
    code: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[BankSecretWriteResult]:
    """Remove the DB-stored secret. Env fallback (if any) remains active."""
    normalized = _normalize_bank_code(code)
    row = await session.get(BankSecret, normalized)
    if row is not None:
        await session.delete(row)
        await session.commit()

    has_env = settings.get_pdf_password(normalized) is not None
    return ApiResponse(
        data=BankSecretWriteResult(
            bank_code=normalized,
            effective_source="env" if has_env else "none",
        )
    )


@router.post("/import-from-env", response_model=ApiResponse[ImportFromEnvResult])
async def import_from_env(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[ImportFromEnvResult]:
    """Bulk-encrypt all env-only ``PDF_PASSWORD_<CODE>`` entries into DB rows."""
    env_codes = _scan_env_codes(settings)
    existing_codes = {
        c for (c,) in (await session.execute(select(BankSecret.bank_code))).all()
    }

    imported: list[str] = []
    skipped = 0
    for code in sorted(env_codes):
        if code in existing_codes:
            skipped += 1
            continue
        plaintext = settings.get_pdf_password(code)
        if not plaintext:
            # Defensive: env-map race condition could clear value mid-call.
            continue
        cipher = settings.master_key_manager.encrypt(plaintext)
        session.add(BankSecret(bank_code=code, encrypted_password=cipher))
        imported.append(code)
    if imported:
        await session.commit()
    logger.info(
        "import-from-env done",
        extra={"imported": len(imported), "skipped": skipped},
    )
    return ApiResponse(
        data=ImportFromEnvResult(
            imported=len(imported),
            skipped_already_in_db=skipped,
            bank_codes_imported=imported,
        )
    )
