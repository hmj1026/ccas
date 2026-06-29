"""DbProgressReporter 單元測試。

覆蓋 stage_started / stage_item_done（節流）/ stage_finished（含 row 缺失、
預設 counts/errors、database-locked 重試與放棄）路徑。每筆 hook 使用獨立
short-lived session，本測試以可控的 ``_FakeSession`` / ``_FakeRow`` 模擬。
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from ccas.pipeline.progress import AsyncSessionFactory, DbProgressReporter


class _FakeSession:
    """Async-context-manager session stub with awaitable execute/commit/get."""

    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.get = AsyncMock()

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeRow:
    """Stand-in for a ``PipelineRun`` ORM row used by stage_finished."""

    def __init__(self, *, stage_summary: list | None = None, total: int = 10) -> None:
        self.stage_summary = stage_summary
        self.current_stage_total = total
        self.current_stage_processed = 0


def _locked_error() -> OperationalError:
    return OperationalError("UPDATE", {}, Exception("database is locked"))


class TestStageStarted:
    """stage_started 即時 flush 並重置節流窗口。"""

    async def test_writes_and_resets_throttle(self):
        session = _FakeSession()
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        await reporter.stage_started("parse", 10)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

        # 重置節流窗口後，下一筆 item_done 立即觸發（不被前一階段卡住）
        await reporter.stage_item_done("parse", 1)
        assert session.execute.await_count == 2


class TestStageItemDone:
    """stage_item_done 的 250ms 節流行為。"""

    async def test_throttle_suppresses_rapid_calls(self):
        session = _FakeSession()
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session), throttle_seconds=100.0
        )

        await reporter.stage_item_done("parse", 1)  # 首筆寫入
        await reporter.stage_item_done("parse", 2)  # 節流抑制

        assert session.execute.await_count == 1

    async def test_no_throttle_writes_each(self):
        session = _FakeSession()
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session), throttle_seconds=0.0
        )

        await reporter.stage_item_done("parse", 1)
        await reporter.stage_item_done("parse", 2)

        assert session.execute.await_count == 2


class TestStageFinished:
    """stage_finished 追加摘要、覆寫進度與 database-locked 重試。"""

    async def test_appends_entry_and_overwrites_progress(self):
        row = _FakeRow(total=10)
        session = _FakeSession()
        session.get = AsyncMock(return_value=row)
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        await reporter.stage_finished(
            "parse",
            ok=9,
            fail=1,
            elapsed_ms=123,
            counts={"parsed": 9},
            errors=["e1"],
        )

        assert row.stage_summary == [
            {
                "stage": "parse",
                "ok": 9,
                "fail": 1,
                "elapsed_ms": 123,
                "counts": {"parsed": 9},
                "errors": ["e1"],
            }
        ]
        assert row.current_stage_processed == 10
        session.commit.assert_awaited_once()

    async def test_appends_to_existing_summary(self):
        existing = [
            {
                "stage": "ingest",
                "ok": 1,
                "fail": 0,
                "elapsed_ms": 1,
                "counts": {},
                "errors": [],
            }
        ]
        row = _FakeRow(stage_summary=existing, total=5)
        session = _FakeSession()
        session.get = AsyncMock(return_value=row)
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        await reporter.stage_finished("parse", 2, 0, 3)

        assert row.stage_summary is not None
        assert len(row.stage_summary) == 2
        assert row.stage_summary[0]["stage"] == "ingest"
        assert row.stage_summary[1]["stage"] == "parse"
        assert row.current_stage_processed == 5

    async def test_default_counts_and_errors(self):
        row = _FakeRow()
        session = _FakeSession()
        session.get = AsyncMock(return_value=row)
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        await reporter.stage_finished("notify", 2, 0, 5)

        assert row.stage_summary is not None
        entry = row.stage_summary[0]
        assert entry["counts"] == {}
        assert entry["errors"] == []

    async def test_missing_row_logs_and_returns(self):
        session = _FakeSession()
        session.get = AsyncMock(return_value=None)
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        await reporter.stage_finished("parse", 1, 0, 10)

        session.commit.assert_not_awaited()

    async def test_retries_on_database_locked_then_succeeds(self):
        # 第一個 session commit 觸發 locked，第二個 session 成功。
        # 各 session 持有獨立 row 以模擬失敗交易 rollback（不污染最終 row）。
        locked_row = _FakeRow(total=4)
        good_row = _FakeRow(total=4)
        locked = _FakeSession()
        locked.get = AsyncMock(return_value=locked_row)
        locked.commit = AsyncMock(side_effect=_locked_error())
        good = _FakeSession()
        good.get = AsyncMock(return_value=good_row)
        sessions = iter([locked, good])
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: next(sessions))
        )

        with patch(
            "ccas.pipeline.progress.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            await reporter.stage_finished("parse", 1, 0, 2)

        sleep.assert_awaited_once()
        good.commit.assert_awaited_once()
        assert good_row.stage_summary is not None
        assert len(good_row.stage_summary) == 1
        assert good_row.current_stage_processed == 4

    async def test_non_locked_operational_error_propagates(self):
        row = _FakeRow()
        session = _FakeSession()
        session.get = AsyncMock(return_value=row)
        session.commit = AsyncMock(
            side_effect=OperationalError("UPDATE", {}, Exception("syntax error"))
        )
        reporter = DbProgressReporter(
            "run-1", cast(AsyncSessionFactory, lambda: session)
        )

        with pytest.raises(OperationalError):
            await reporter.stage_finished("parse", 1, 0, 2)

    async def test_gives_up_after_max_retries(self):
        row = _FakeRow()

        def factory() -> _FakeSession:
            session = _FakeSession()
            session.get = AsyncMock(return_value=row)
            session.commit = AsyncMock(side_effect=_locked_error())
            return session

        reporter = DbProgressReporter("run-1", cast(AsyncSessionFactory, factory))

        with patch("ccas.pipeline.progress.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await reporter.stage_finished("parse", 1, 0, 2)
