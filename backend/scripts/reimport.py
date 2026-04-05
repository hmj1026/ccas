"""從已下載的 staged PDF 重新匯入帳單資料。

Usage:
    uv run python backend/scripts/reimport.py            # 重匯所有銀行
    uv run python backend/scripts/reimport.py --bank CTBC  # 僅重匯 CTBC

流程：
1. 確認 BankConfig + Categories 存在（警告但不中止）
2. 清空 Bills + Transactions（保留 BankConfig, Categories, StagedAttachments）
3. 重設 StagedAttachment.status: "parsed"/"parse_failed" → "decrypted"
4. 執行 parse job（force=False，因已清空，不會衝突）
5. 執行 classify job（全 NULL，直接分類）
6. 輸出統計摘要
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.classifier.job import run_classify_job
from ccas.config import get_settings
from ccas.parser.job import run_parse_job
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    Category,
    StagedAttachment,
    Transaction,
)


async def _check_prerequisites(session: AsyncSession, bank_code: str | None) -> None:
    """確認 BankConfig 與 Categories 存在，若缺失則印出警告。"""
    stmt = select(func.count()).select_from(BankConfig)
    if bank_code:
        stmt = stmt.where(BankConfig.bank_code == bank_code)
    config_count = (await session.execute(stmt)).scalar_one()
    if config_count == 0:
        label = f"bank_code={bank_code}" if bank_code else "任何銀行"
        print(f"  [警告] 找不到 BankConfig（{label}），parse 可能失敗")

    cat_count = (await session.execute(select(func.count()).select_from(Category))).scalar_one()
    if cat_count == 0:
        print("  [警告] Categories 資料表為空，classify 結果將全為 NULL")


async def clear_bills_and_transactions(session: AsyncSession) -> tuple[int, int]:
    """清空 Bills 與 Transactions（依 FK 順序）。

    Returns:
        (bill_count, txn_count) 已刪除的筆數。
    """
    txn_count = (await session.execute(select(func.count()).select_from(Transaction))).scalar_one()
    bill_count = (await session.execute(select(func.count()).select_from(Bill))).scalar_one()

    await session.execute(delete(Transaction))
    await session.execute(delete(Bill))
    await session.commit()

    return bill_count, txn_count


async def reset_staged_statuses(
    session: AsyncSession,
    bank_code: str | None = None,
) -> int:
    """將 StagedAttachment.status 由 "parsed"/"parse_failed" 重設為 "decrypted"。

    Args:
        session: 非同步 DB Session。
        bank_code: 若指定則只重設該銀行的附件。

    Returns:
        已重設的附件數量。
    """
    stmt = (
        update(StagedAttachment)
        .where(StagedAttachment.status.in_(["parsed", "parse_failed"]))
        .values(status="decrypted", error_reason=None)
    )
    if bank_code:
        stmt = stmt.where(StagedAttachment.bank_code == bank_code)

    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reimport CTBC bills from staged PDFs into the database.",
    )
    parser.add_argument(
        "--bank",
        type=str,
        default=None,
        metavar="BANK_CODE",
        help="Only reimport the specified bank (e.g., CTBC). Default: all banks.",
    )
    return parser.parse_args()


async def main(*, bank_code: str | None = None) -> None:
    """執行 reimport 流程並輸出統計。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        print("Checking prerequisites...")
        await _check_prerequisites(session, bank_code)

        print("Clearing bills and transactions...")
        bill_count, txn_count = await clear_bills_and_transactions(session)
        print(f"  Deleted {bill_count} bill(s) and {txn_count} transaction(s)")

        print("Resetting staged attachment statuses...")
        reset_count = await reset_staged_statuses(session, bank_code)
        print(f"  Reset {reset_count} attachment(s) to 'decrypted'")

        print("Running parse job...")
        options = PipelineOptions(bank_code=bank_code, force=False)
        parse_summary = await run_parse_job(session, options)
        print(
            f"  Parsed: {parse_summary.parsed_count}, "
            f"Skipped: {parse_summary.skipped_count}, "
            f"Failed: {parse_summary.failed_count}"
        )
        if parse_summary.errors:
            for err in parse_summary.errors:
                print(f"  [Error] {err}")

        print("Running classify job...")
        classify_summary = await run_classify_job(session)
        print(f"  Classified: {classify_summary.classified_count} transaction(s)")

        # Final counts
        final_bills = (await session.execute(select(func.count()).select_from(Bill))).scalar_one()
        final_txns = (await session.execute(select(func.count()).select_from(Transaction))).scalar_one()
        print(f"Done. DB now has {final_bills} bill(s) and {final_txns} transaction(s).")

    await engine.dispose()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(bank_code=args.bank))
