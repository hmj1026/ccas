"""CLI 模組入口：python -m ccas.pipeline

同步呼叫 run_pipeline() 並將摘要輸出至 stdout。
"""

import argparse
import asyncio
import json
import sys

from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.orchestrator import run_pipeline
from ccas.pipeline.summary import PipelineSummary
from ccas.storage.database import get_engine, get_session_factory


def _summary_to_dict(summary: PipelineSummary) -> dict:
    """將 PipelineSummary 轉為可序列化的 dict。"""
    return {
        "total_seconds": summary.total_seconds,
        "stages": [
            {"stage": s.stage, "counts": s.counts, "errors": s.errors}
            for s in summary.stages
        ],
        "failures": [
            {"item_id": f.item_id, "error": f.error} for f in summary.failures
        ],
    }


def _parse_args(argv: list[str] | None = None) -> PipelineOptions:
    """解析 CLI 參數並回傳 PipelineOptions。"""
    parser = argparse.ArgumentParser(
        prog="python -m ccas.pipeline",
        description="Execute the CCAS bill processing pipeline.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-download and re-parse, bypassing deduplication.",
    )
    parser.add_argument(
        "--bank",
        type=str,
        default=None,
        metavar="BANK_CODE",
        help="Only process the specified bank (e.g., CTBC).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        metavar="YYYY",
        help="Filter Gmail messages by year.",
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        choices=range(1, 13),
        metavar="MM",
        help="Filter Gmail messages by month (1-12).",
    )
    args = parser.parse_args(argv)
    if args.year is not None and not (2000 <= args.year <= 2099):
        parser.error(f"year must be between 2000 and 2099, got {args.year}")
    return PipelineOptions(
        force=args.force,
        bank_code=args.bank,
        year=args.year,
        month=args.month,
    )


async def _main(options: PipelineOptions) -> PipelineSummary:
    session_factory = get_session_factory()
    async with session_factory() as session:
        summary = await run_pipeline(session, options)
    await get_engine().dispose()
    return summary


def main() -> None:
    """CLI 入口：同步執行 pipeline 並輸出 JSON 摘要。"""
    options = _parse_args()
    summary = asyncio.run(_main(options))
    print(json.dumps(_summary_to_dict(summary), ensure_ascii=False, indent=2))
    # Non-zero exit if any failures
    if summary.failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
