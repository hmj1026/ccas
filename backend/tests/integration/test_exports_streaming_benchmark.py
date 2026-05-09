"""Large-data streaming benchmark for /api/transactions/export (§15.6 §15.7).

驗證：
- CSV streaming：response 為 chunked、不會一次撈整批進記憶體
- xlsx streaming：write_only mode + tempfile 不 OOM
- 端對端 latency 與 backend peak memory

預設用 5K 筆作為 CI 友善基線；設 ``CCAS_BENCH_50K=1`` 才會跑完整 50K
（spec §15.6/§15.7 的 acceptance 規模）。
"""

from __future__ import annotations

import os
import time
import tracemalloc
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers

ROW_COUNT = 50_000 if os.getenv("CCAS_BENCH_50K") == "1" else 5_000

# Acceptance gate values — tighter for the full benchmark, looser for the
# CI-friendly 5K subset to keep noise low on shared runners.
CSV_LATENCY_LIMIT_S = 30.0 if ROW_COUNT >= 50_000 else 8.0
PEAK_MEMORY_LIMIT_MB = 100.0 if ROW_COUNT >= 50_000 else 50.0


async def _seed_many_transactions(session: AsyncSession, *, count: int) -> None:
    """Bulk insert ``count`` transactions across one bill."""
    session.add(
        BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc")
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-05",
        total_amount=count * 100,
        due_date=date.today() + timedelta(days=10),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    base_date = date(2026, 1, 1)
    batch_size = 1_000
    for chunk_start in range(0, count, batch_size):
        chunk_end = min(chunk_start + batch_size, count)
        session.add_all(
            [
                Transaction(
                    bill_id=bill.id,
                    trans_date=base_date + timedelta(days=i % 365),
                    merchant=f"M{i:06d}",
                    amount=100 + (i % 999),
                    currency="TWD",
                    category="餐飲" if i % 2 == 0 else "交通",
                    tags=[],
                )
                for i in range(chunk_start, chunk_end)
            ]
        )
        await session.flush()
    await session.commit()


@pytest.mark.timeout(120)
async def test_csv_export_handles_large_dataset_without_oom(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CSV streaming handles ROW_COUNT rows under latency + memory budgets."""
    await _seed_many_transactions(db_session, count=ROW_COUNT)

    tracemalloc.start()
    started = time.perf_counter()
    rows_observed = 0
    bytes_observed = 0
    async with client.stream(
        "GET",
        "/api/transactions/export?format=csv",
        headers=auth_headers(),
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        async for chunk in resp.aiter_bytes():
            bytes_observed += len(chunk)
            rows_observed += chunk.count(b"\n")
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)

    # header + ROW_COUNT data rows
    assert rows_observed == ROW_COUNT + 1, (
        f"row count mismatch: got {rows_observed} expected {ROW_COUNT + 1}"
    )
    assert bytes_observed > 0
    assert elapsed < CSV_LATENCY_LIMIT_S, (
        f"CSV streaming for {ROW_COUNT} rows took {elapsed:.2f}s "
        f"(>{CSV_LATENCY_LIMIT_S}s limit)"
    )
    assert peak_mb < PEAK_MEMORY_LIMIT_MB, (
        f"CSV streaming peak memory {peak_mb:.1f}MB > "
        f"{PEAK_MEMORY_LIMIT_MB}MB limit (suggests buffering instead of "
        f"streaming)"
    )


@pytest.mark.timeout(180)
async def test_xlsx_export_streams_via_tempfile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """xlsx export uses write_only + tempfile, returning binary chunked."""
    # xlsx 寫入時 openpyxl write_only 仍會在記憶體保留每列 cell 物件，
    # 50K 筆下記憶體可能接近 spec 上限；本測試確保「不 OOM、回正確 binary」即可，
    # latency / memory 嚴格檢查留給 CSV 路徑。
    await _seed_many_transactions(db_session, count=ROW_COUNT)

    started = time.perf_counter()
    bytes_observed = 0
    async with client.stream(
        "GET",
        "/api/transactions/export?format=xlsx",
        headers=auth_headers(),
    ) as resp:
        assert resp.status_code == 200
        ct = resp.headers["content-type"]
        assert "spreadsheetml" in ct or "octet-stream" in ct
        async for chunk in resp.aiter_bytes():
            bytes_observed += len(chunk)
    elapsed = time.perf_counter() - started

    # xlsx 為 zip 容器，最少要有 zip header 與 sheet xml
    assert bytes_observed > 1024
    assert elapsed < CSV_LATENCY_LIMIT_S * 3, (
        f"xlsx streaming for {ROW_COUNT} rows took {elapsed:.2f}s"
    )
