"""Stage job ProgressReporter 內部 emit 測試（pipeline-operations-center §3A.6）。

每個 stage job 在 outer item loop 內必須：
1. 在 loop 之前發 ``stage_started(stage, total=len(items))``
2. 每處理一個 item 發 ``stage_item_done(stage, processed=N)``，``processed``
   單調遞增至 ``total``
3. item-level failure 不卡 processed counter（§3A.7）：失敗仍 +1

Ingest 的 total / processed 為「per-bank reset」，跨 bank 重啟（spec D11）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.bot.job import run_notify_job
from ccas.classifier.job import run_classify_job
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.decryptor.job import run_decryption_job
from ccas.ingestor.job import run_ingestion_job
from ccas.parser.job import run_parse_job

from .conftest import FakeReporter
from .conftest import items as _items
from .conftest import started_total as _started_total

# Empty user-rule matcher; bills-management-and-insights §2.4 注入點，
# 既有 stage progress 測試只在乎 keyword engine 流程，user rules 走 noop。
_EMPTY_MATCHER = UserRuleMatcher([])

# --- classify ---------------------------------------------------------------


async def test_classify_emits_started_total_and_monotonic_processed() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    txns: Sequence[Any] = [
        MagicMock(id=1, merchant="STARBUCKS", manual_category_override=False),
        MagicMock(id=2, merchant="MRT", manual_category_override=False),
        MagicMock(id=3, merchant="UBER EATS", manual_category_override=False),
    ]

    with (
        patch(
            "ccas.classifier.job.UserRuleMatcher.load",
            new=AsyncMock(return_value=_EMPTY_MATCHER),
        ),
        patch("ccas.classifier.job.load_rules", new=AsyncMock(return_value={})),
        patch(
            "ccas.classifier.job.fetch_unclassified_transactions",
            new=AsyncMock(return_value=txns),
        ),
        patch("ccas.classifier.job.classify", new=lambda m, r: "其他"),
    ):
        result = await run_classify_job(session, reporter=reporter)

    assert _started_total(reporter, "classify") == 3
    assert _items(reporter, "classify") == [1, 2, 3]
    assert result.classified_count == 3


async def test_classify_empty_emits_started_zero_no_items() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    with (
        patch(
            "ccas.classifier.job.UserRuleMatcher.load",
            new=AsyncMock(return_value=_EMPTY_MATCHER),
        ),
        patch("ccas.classifier.job.load_rules", new=AsyncMock(return_value={})),
        patch(
            "ccas.classifier.job.fetch_unclassified_transactions",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await run_classify_job(session, reporter=reporter)

    assert _started_total(reporter, "classify") == 0
    assert _items(reporter, "classify") == []


async def test_classify_item_failure_does_not_stall_processed() -> None:
    """§3A.7: classify 引擎 raise 時 processed 仍遞增。"""
    reporter = FakeReporter()
    session = AsyncMock()

    txns = [
        MagicMock(id=1, merchant="A", manual_category_override=False),
        MagicMock(id=2, merchant="B", manual_category_override=False),
        MagicMock(id=3, merchant="C", manual_category_override=False),
    ]

    def raising_classify(merchant: str, _rules: Any) -> str:
        if merchant == "B":
            raise RuntimeError("classify boom")
        return "OK"

    with (  # noqa: SIM117
        patch(
            "ccas.classifier.job.UserRuleMatcher.load",
            new=AsyncMock(return_value=_EMPTY_MATCHER),
        ),
        patch("ccas.classifier.job.load_rules", new=AsyncMock(return_value={})),
        patch(
            "ccas.classifier.job.fetch_unclassified_transactions",
            new=AsyncMock(return_value=txns),
        ),
        patch("ccas.classifier.job.classify", new=raising_classify),
    ):
        with pytest.raises(RuntimeError):
            await run_classify_job(session, reporter=reporter)

    # Processed counter advances even when the raising item triggers finally.
    items = _items(reporter, "classify")
    assert items == [1, 2]


# --- decrypt ----------------------------------------------------------------


async def test_decrypt_emits_started_and_per_attachment_progress() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    attachments = [MagicMock(id=i) for i in range(4)]

    with (
        patch(
            "ccas.decryptor.job.fetch_pending_attachments",
            new=AsyncMock(return_value=attachments),
        ),
        # Stage 3 item C: run_decryption_job pre-resolves passwords per distinct
        # bank_code into a cache before the loop. Patch it so this progress-hook
        # test stays isolated from Fernet/password resolution.
        patch(
            "ccas.decryptor.job.resolve_passwords",
            new=AsyncMock(return_value=("pw",)),
        ),
        patch(
            "ccas.decryptor.job._process_attachment", new=AsyncMock(return_value=None)
        ),
    ):
        await run_decryption_job(session, options=None, reporter=reporter)

    assert _started_total(reporter, "decrypt") == 4
    assert _items(reporter, "decrypt") == [1, 2, 3, 4]


async def test_decrypt_empty_emits_started_zero() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    with patch(
        "ccas.decryptor.job.fetch_pending_attachments",
        new=AsyncMock(return_value=[]),
    ):
        await run_decryption_job(session, options=None, reporter=reporter)

    assert _started_total(reporter, "decrypt") == 0
    assert _items(reporter, "decrypt") == []


# --- parse ------------------------------------------------------------------


async def test_parse_emits_started_and_per_attachment_progress() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    attachments = [MagicMock(id=i) for i in range(2)]

    with (
        patch(
            "ccas.parser.job.fetch_parseable_attachments",
            new=AsyncMock(return_value=attachments),
        ),
        patch("ccas.parser.job._process_attachment", new=AsyncMock(return_value=None)),
    ):
        await run_parse_job(session, options=None, reporter=reporter)

    assert _started_total(reporter, "parse") == 2
    assert _items(reporter, "parse") == [1, 2]


# --- notify -----------------------------------------------------------------


async def test_notify_emits_started_total_for_unnotified_bills() -> None:
    reporter = FakeReporter()

    bills = [
        MagicMock(
            id=1,
            bank_code="CTBC",
            billing_month="2025-04",
            total_amount=1000,
            due_date="2025-05-15",
        ),
        MagicMock(
            id=2,
            bank_code="ESUN",
            billing_month="2025-04",
            total_amount=2000,
            due_date="2025-05-20",
        ),
    ]

    session = AsyncMock()

    # session.execute returns a result object whose .scalars().all() returns bills.
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = bills
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    with (
        patch(
            "ccas.bot.job.fetch_bank_names",
            new=AsyncMock(return_value={"CTBC": "中國信託", "ESUN": "玉山"}),
        ),
        patch("ccas.bot.job.send_message", new=AsyncMock(return_value=None)),
    ):
        await run_notify_job(session, reporter=reporter)

    assert _started_total(reporter, "notify") == 2
    assert _items(reporter, "notify") == [1, 2]


async def test_notify_disabled_settings_emits_started_zero() -> None:
    """When TELEGRAM_BOT_TOKEN/CHAT_ID are unset notify SHALL emit total=0."""
    reporter = FakeReporter()
    session = AsyncMock()

    fake_settings = MagicMock()
    fake_settings.telegram_bot_token = ""
    fake_settings.telegram_chat_id = ""

    with patch("ccas.bot.job.get_settings", return_value=fake_settings):
        await run_notify_job(session, reporter=reporter)

    assert _started_total(reporter, "notify") == 0
    assert _items(reporter, "notify") == []


# --- ingest -----------------------------------------------------------------


async def test_ingest_emits_per_bank_started_with_attachment_total() -> None:
    """Spec D11 / §3A.1: stage_started fires once per bank with that bank's
    attachment total; processed resets across banks."""
    reporter = FakeReporter()
    session = AsyncMock()

    bank_a = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
    bank_b = MagicMock(bank_code="ESUN", gmail_filter="from:esun")

    msg_a1 = MagicMock(pdf_attachments=[MagicMock(), MagicMock()], html_body=None)
    msg_b1 = MagicMock(pdf_attachments=[MagicMock()], html_body=None)
    msg_b2 = MagicMock(pdf_attachments=[], html_body="<html>fallback</html>")

    bank_messages = {"from:ctbc": [msg_a1], "from:esun": [msg_b1, msg_b2]}

    def _search(
        _service: Any,
        query: str,
        *,
        bank_code: str | None = None,
        partial_errors: Any = None,
    ) -> list[Any]:
        return bank_messages[query]

    with (
        patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
        patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
        patch(
            "ccas.ingestor.job._fetch_active_banks",
            new=AsyncMock(return_value=[bank_a, bank_b]),
        ),
        patch("ccas.ingestor.job.search_messages", side_effect=_search),
        patch(
            "ccas.ingestor.job._process_attachment",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "ccas.ingestor.job._process_web_fetch",
            new=AsyncMock(return_value=None),
        ),
    ):
        await run_ingestion_job(session, options=None, reporter=reporter)

    started_calls = [
        payload for kind, payload in reporter.calls if kind == "stage_started"
    ]
    # Two banks → two stage_started, totals 2 (CTBC) and 2 (ESUN: 1 pdf + 1 html).
    assert [p["total"] for p in started_calls] == [2, 2]

    # First bank emits item events 1, 2, then second bank resets to 1, 2.
    item_events = [
        payload["processed"]
        for kind, payload in reporter.calls
        if kind == "stage_item_done"
    ]
    assert item_events == [1, 2, 1, 2]


async def test_ingest_no_active_banks_emits_zero_total() -> None:
    reporter = FakeReporter()
    session = AsyncMock()

    with (
        patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
        patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
        patch("ccas.ingestor.job._fetch_active_banks", new=AsyncMock(return_value=[])),
    ):
        result = await run_ingestion_job(session, options=None, reporter=reporter)

    assert _started_total(reporter, "ingest") == 0
    assert _items(reporter, "ingest") == []
    assert result.banks_processed == 0


async def test_ingest_item_failure_advances_processed() -> None:
    """§3A.7: ingestion attachment processing raise → processed still +1.

    Stage 3 item B makes the per-item failure resilient: an unexpected raise in
    one attachment is rolled back and the batch CONTINUES to the next item (the
    job no longer propagates the exception). The progress counter still advances
    for every item via the innermost finally.
    """
    reporter = FakeReporter()
    session = AsyncMock()

    bank_a = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
    msg = MagicMock(pdf_attachments=[MagicMock(), MagicMock()], html_body=None)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("attachment boom")

    with (
        patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
        patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
        patch(
            "ccas.ingestor.job._fetch_active_banks",
            new=AsyncMock(return_value=[bank_a]),
        ),
        patch("ccas.ingestor.job.search_messages", return_value=[msg]),
        patch("ccas.ingestor.job._process_attachment", side_effect=boom),
    ):
        # No longer raises: both failing items are rolled back and skipped.
        await run_ingestion_job(session, options=None, reporter=reporter)

    # Both attachments advanced the processed counter (innermost finally ran for
    # each), and each failure triggered a rollback.
    assert _items(reporter, "ingest") == [1, 2]
    assert session.rollback.await_count == 2
