"""Bank-management router (oauth-onboarding-ui §4).

Surfaces ``bank_configs`` metadata + ``bank_settings`` user preferences in a
single list, plus an UPSERT endpoint for the enabled toggle / display name.

Precedence for the ``enabled`` field that the UI shows:

1. ``bank_settings.enabled`` (DB row owned by user)
2. ``bank_configs.is_active`` (seeded from ``config/banks.yaml``)
3. Default ``True``

The same precedence is applied at ingestor entry by
``ccas.ingestor.job._apply_bank_settings_filter``; this router only surfaces
state, it does not run that filter (the wire-up lives where it matters most).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankSettingsUpdateRequest,
    SetupBankItem,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import BankConfig, BankSettings, StagedAttachment

router = APIRouter(prefix="/api/setup/banks", tags=["setup-banks"])


def _ensure_aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; force UTC for serialization."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@router.get("", response_model=ApiResponse[list[SetupBankItem]])
async def list_setup_banks(
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[SetupBankItem]]:
    """Return per-bank setup state (metadata + user toggle + ingest stats)."""
    config_rows = (await session.execute(select(BankConfig))).scalars().all()
    settings_rows = (await session.execute(select(BankSettings))).scalars().all()
    stats_rows = (
        await session.execute(
            select(
                StagedAttachment.bank_code,
                func.count(StagedAttachment.id),
                func.max(StagedAttachment.message_date),
            ).group_by(StagedAttachment.bank_code)
        )
    ).all()

    settings_by_code = {row.code: row for row in settings_rows}
    configs_by_code = {row.bank_code: row for row in config_rows}
    stats_by_code = {code: (count, last_at) for code, count, last_at in stats_rows}

    all_codes = set(configs_by_code) | set(settings_by_code)
    items: list[SetupBankItem] = []
    for code in sorted(all_codes):
        config = configs_by_code.get(code)
        settings_row = settings_by_code.get(code)
        total, last_at = stats_by_code.get(code, (0, None))
        if settings_row is not None:
            enabled = settings_row.enabled
            display_name = settings_row.display_name or (
                config.bank_name if config is not None else None
            )
        else:
            enabled = config.is_active if config is not None else True
            display_name = config.bank_name if config is not None else None
        items.append(
            SetupBankItem(
                code=code,
                display_name=display_name,
                enabled=enabled,
                has_settings_row=settings_row is not None,
                metadata_missing=config is None,
                total_pdfs=int(total),
                last_ingest_at=_ensure_aware(last_at),
            )
        )
    return ApiResponse(data=items)


@router.put("/{code}", response_model=ApiResponse[SetupBankItem])
async def update_setup_bank(
    code: str,
    payload: BankSettingsUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SetupBankItem]:
    """Upsert a ``bank_settings`` row; returns the merged view of that bank."""
    normalized = code.strip().upper()
    if not normalized:
        raise HTTPException(status_code=422, detail="bank code 不可為空")

    # Race-safe UPSERT: SQLite ON CONFLICT DO UPDATE collapses the
    # read-modify-write into a single atomic statement. Concurrent PUT
    # requests for the same `code` no longer fight for INSERT.
    update_set: dict[str, object] = {"enabled": payload.enabled}
    if payload.display_name is not None:
        update_set["display_name"] = payload.display_name
    if payload.notes is not None:
        update_set["notes"] = payload.notes
    stmt = sqlite_insert(BankSettings).values(
        code=normalized,
        enabled=payload.enabled,
        display_name=payload.display_name,
        notes=payload.notes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[BankSettings.code], set_=update_set
    )
    await session.execute(stmt)
    await session.commit()
    row = await session.get(BankSettings, normalized)
    if row is None:
        raise HTTPException(
            status_code=500, detail="UPSERT 後無法取回 bank_settings row"
        )

    # bank_configs.bank_code is unique but not the PK; fetch by where().
    config_result = await session.execute(
        select(BankConfig).where(BankConfig.bank_code == normalized)
    )
    config = config_result.scalar_one_or_none()

    stats_result = await session.execute(
        select(
            func.count(StagedAttachment.id),
            func.max(StagedAttachment.message_date),
        ).where(StagedAttachment.bank_code == normalized)
    )
    total, last_at = stats_result.one()

    return ApiResponse(
        data=SetupBankItem(
            code=normalized,
            display_name=row.display_name
            or (config.bank_name if config is not None else None),
            enabled=row.enabled,
            has_settings_row=True,
            metadata_missing=config is None,
            total_pdfs=int(total or 0),
            last_ingest_at=_ensure_aware(last_at),
        )
    )
