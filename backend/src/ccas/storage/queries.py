"""Shared database query helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig


async def fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    """Query bank_code -> bank_name mapping for all banks."""
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}
