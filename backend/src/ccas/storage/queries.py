"""Shared database query helpers."""

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig

# Single-entry TTL cache for fetch_bank_names. Bank configs change rarely
# (YAML sync / setup UI) while the mapping is read on nearly every API
# request, bot command, and scheduler run.
_BANK_NAMES_TTL_SECONDS = 300.0
_BANK_NAMES_CACHE_KEY = "bank_names"
_bank_names_cache: dict[str, tuple[float, dict[str, str]]] = {}


def invalidate_bank_names_cache() -> None:
    """Drop the cached bank name mapping.

    Call after any write to ``bank_configs`` (e.g. ``sync_bank_configs``)
    so readers see fresh names without waiting for the TTL to lapse.
    """
    _bank_names_cache.clear()


async def fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    """Query bank_code -> bank_name mapping for all banks.

    Results are cached module-wide for ``_BANK_NAMES_TTL_SECONDS`` seconds.
    A fresh copy is returned on every call so callers may mutate the dict
    without poisoning the cache.
    """
    entry = _bank_names_cache.get(_BANK_NAMES_CACHE_KEY)
    if entry is not None and time.monotonic() < entry[0]:
        return dict(entry[1])

    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    mapping = {row[0]: row[1] for row in result.all()}
    _bank_names_cache[_BANK_NAMES_CACHE_KEY] = (
        time.monotonic() + _BANK_NAMES_TTL_SECONDS,
        mapping,
    )
    return dict(mapping)
