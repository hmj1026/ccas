"""Re-run classification for all existing transactions.

Re-loads the latest keyword rules from the categories table and
re-classifies every transaction. Only the `category` column is
updated; original transaction data is not modified.
"""

from __future__ import annotations

import argparse
import asyncio

from ccas.classifier.job import run_reclassify_job
from ccas.storage.database import get_engine, get_session_factory


async def _run_cli() -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        summary = await run_reclassify_job(session)
    await get_engine().dispose()
    print(
        f"重跑分類完成: classified={summary.classified_count}"
        f" skipped={summary.skipped_count}"
        f" total={summary.total_count}"
    )


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(
        description="對所有既有交易重跑分類（重新載入最新規則）。"
    ).parse_args(argv)
    asyncio.run(_run_cli())


if __name__ == "__main__":
    main()
