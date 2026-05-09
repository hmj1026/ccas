"""Cleanup expired ``gmail_oauth_state`` rows（oauth-onboarding-ui §3.8）。

OAuth state row 在 callback 成功後會被 router 主動刪除；此 CLI 為「總體
掃除」用：刪除 ``created_at`` 超過 1 天的條目，避免使用者多次點擊「授權」
但從未完成 callback 而堆積 row。entrypoint 啟動時呼叫一次，fail-soft。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.database import get_engine, get_session_factory
from ccas.storage.models import GmailOAuthState

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE = timedelta(days=1)


async def cleanup_expired_state(
    session: AsyncSession, max_age: timedelta = DEFAULT_MAX_AGE
) -> int:
    """Delete state rows older than ``max_age``; return number of rows removed."""
    cutoff = datetime.now(UTC) - max_age
    result = await session.execute(
        delete(GmailOAuthState).where(GmailOAuthState.created_at < cutoff)
    )
    # SQLAlchemy 2.0 sets rowcount on the underlying CursorResult; pyright
    # cannot statically narrow Result -> CursorResult, so use getattr fallback.
    return int(getattr(result, "rowcount", 0) or 0)


async def _run_cli(database_url: str | None, max_age_hours: int) -> int:
    if database_url:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        owns_engine = True
    else:
        engine = get_engine()
        factory = get_session_factory()
        owns_engine = False

    try:
        async with factory() as session:
            removed = await cleanup_expired_state(
                session, max_age=timedelta(hours=max_age_hours)
            )
            await session.commit()
    finally:
        if owns_engine:
            await engine.dispose()

    print(f"[cleanup_gmail_state] removed={removed} rows older than {max_age_hours}h")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="清理 gmail_oauth_state 中過期的 OAuth state 條目。"
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="刪除 created_at 早於此時數的條目（預設 24）",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="覆寫資料庫連線字串；未提供時讀取 Settings。",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run_cli(args.database_url, args.max_age_hours))


if __name__ == "__main__":
    raise SystemExit(main())
