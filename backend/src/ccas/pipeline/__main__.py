"""CLI 模組入口：python -m ccas.pipeline

同步呼叫 run_pipeline() 並將摘要輸出至 stdout。
"""

import asyncio
import json
import sys

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
            {"item_id": f.item_id, "error": f.error}
            for f in summary.failures
        ],
    }


async def _main() -> PipelineSummary:
    engine = get_engine()
    session_factory = get_session_factory(engine)
    async with session_factory() as session:
        summary = await run_pipeline(session)
    await engine.dispose()
    return summary


def main() -> None:
    """CLI 入口：同步執行 pipeline 並輸出 JSON 摘要。"""
    summary = asyncio.run(_main())
    print(json.dumps(_summary_to_dict(summary), ensure_ascii=False, indent=2))
    # Non-zero exit if any failures
    if summary.failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
