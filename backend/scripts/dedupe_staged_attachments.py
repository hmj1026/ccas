"""一次性清理 staged_attachments 冗餘列。

歷史背景：在修復 ingest dedupe bug（改用 stable Gmail MIME part_id）之前，
ingestor 每次執行都會為同一附件寫入新的 staged_attachments 列（因為
``gmail_attachment_id`` 每次 Gmail API 呼叫都會重生）。本腳本對每個
``(bank_code, gmail_message_id, original_filename)`` 群組保留 ``id`` 最大
（最新）的一列、刪除其餘，並在無其他列引用同一 ``staged_path`` 時順帶
清理磁碟檔案。

Usage:
    uv run python scripts/dedupe_staged_attachments.py
        # dry-run (default)
    uv run python scripts/dedupe_staged_attachments.py --apply
        # 實際刪除 DB 列 + 檔案
    uv run python scripts/dedupe_staged_attachments.py --apply --keep-files
        # 只刪 DB 列

安全機制：
- 預設為 dry-run，需顯式加 ``--apply`` 才真的寫入
- 檔案刪除僅在該檔案路徑不再被任何保留列引用時執行
- 每個銀行的 before/after 統計會列印
"""

import argparse
import asyncio
import logging
from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.config import get_settings
from ccas.storage.models import StagedAttachment

logger = logging.getLogger("dedupe_staged_attachments")


async def _collect_duplicate_plan(
    session: AsyncSession,
) -> tuple[list[StagedAttachment], list[StagedAttachment], dict[str, tuple[int, int]]]:
    """Compute which rows to keep vs delete.

    Returns:
        (to_keep, to_delete, per_bank_stats)
        per_bank_stats maps bank_code → (rows_before, rows_after)
    """
    all_rows = (
        (await session.execute(select(StagedAttachment).order_by(StagedAttachment.id)))
        .scalars()
        .all()
    )

    # Group by (bank, message_id, filename). For each group keep MAX(id).
    groups: dict[tuple[str, str, str], list[StagedAttachment]] = defaultdict(list)
    for row in all_rows:
        key = (row.bank_code, row.gmail_message_id, row.original_filename)
        groups[key].append(row)

    to_keep: list[StagedAttachment] = []
    to_delete: list[StagedAttachment] = []
    for rows in groups.values():
        rows_sorted = sorted(rows, key=lambda r: r.id)
        to_keep.append(rows_sorted[-1])  # MAX(id) == newest
        to_delete.extend(rows_sorted[:-1])

    per_bank: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    before_counts: dict[str, int] = defaultdict(int)
    after_counts: dict[str, int] = defaultdict(int)
    for row in all_rows:
        before_counts[row.bank_code] += 1
    for row in to_keep:
        after_counts[row.bank_code] += 1
    for bank in set(before_counts) | set(after_counts):
        per_bank[bank] = (before_counts[bank], after_counts[bank])

    return to_keep, to_delete, dict(per_bank)


def _print_plan(
    to_keep: list[StagedAttachment],
    to_delete: list[StagedAttachment],
    per_bank: dict[str, tuple[int, int]],
) -> None:
    print("=" * 60)
    print("Dedupe plan for staged_attachments")
    print("=" * 60)
    print(f"{'Bank':<12}{'Before':>10}{'After':>10}{'Delete':>10}")
    print("-" * 42)
    total_before = total_after = 0
    for bank in sorted(per_bank):
        before, after = per_bank[bank]
        print(f"{bank:<12}{before:>10}{after:>10}{before - after:>10}")
        total_before += before
        total_after += after
    print("-" * 42)
    print(
        f"{'TOTAL':<12}{total_before:>10}{total_after:>10}"
        f"{total_before - total_after:>10}"
    )
    print()
    print(f"Rows to KEEP: {len(to_keep)}")
    print(f"Rows to DELETE: {len(to_delete)}")


async def _apply_deletions(
    session: AsyncSession,
    to_keep: list[StagedAttachment],
    to_delete: list[StagedAttachment],
    keep_files: bool,
) -> int:
    """Delete duplicate DB rows and optionally orphaned files.

    Returns:
        Number of files removed from disk.
    """
    kept_paths = {row.staged_path for row in to_keep if row.staged_path}
    delete_ids = [row.id for row in to_delete]

    files_removed = 0
    if not keep_files:
        for row in to_delete:
            if not row.staged_path:
                continue
            if row.staged_path in kept_paths:
                continue
            path = Path(row.staged_path)
            if path.exists():
                try:
                    path.unlink()
                    files_removed += 1
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", path, exc)

    if delete_ids:
        await session.execute(
            delete(StagedAttachment).where(StagedAttachment.id.in_(delete_ids))
        )
        await session.commit()

    return files_removed


async def main_async(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        to_keep, to_delete, per_bank = await _collect_duplicate_plan(session)
        _print_plan(to_keep, to_delete, per_bank)

        if not to_delete:
            print("\nNothing to clean up.")
            return

        if not args.apply:
            print("\n[DRY-RUN] No changes written. Re-run with --apply to execute.")
            return

        files_removed = await _apply_deletions(
            session, to_keep, to_delete, keep_files=args.keep_files
        )
        print(
            f"\n[APPLIED] Deleted {len(to_delete)} DB rows, "
            f"removed {files_removed} orphan files."
        )

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Clean up duplicate staged_attachments rows that accumulated before "
            "the gmail_part_id dedupe fix."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows and files (default is dry-run).",
    )
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Only delete DB rows; leave staging files on disk untouched.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
