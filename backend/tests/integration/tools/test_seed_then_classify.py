"""Verify user-guide troubleshooting: seed then reclassify."""

from datetime import date
from pathlib import Path

import pytest

from ccas.classifier.job import run_reclassify_job
from ccas.storage.models import Bill, Transaction
from ccas.tools.categories import apply_categories, load_category_specs

YAML_CONTENT = """\
categories:
  - category: 餐飲
    keywords:
      - 麥當勞
      - 星巴克
  - category: 超商
    keywords:
      - 統一超商
"""


@pytest.fixture
def categories_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "categories.yaml"
    path.write_text(YAML_CONTENT, encoding="utf-8")
    return path


async def test_seed_then_reclassify_updates_transactions(
    db_session, categories_yaml
) -> None:
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=1000,
        due_date=date(2026, 4, 15),
    )
    db_session.add(bill)
    await db_session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="麥當勞台北站前店",
            amount=150,
            category=None,
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 2),
            merchant="統一超商忠孝門市",
            amount=65,
            category=None,
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 3),
            merchant="不知名商店",
            amount=200,
            category=None,
        ),
    ]
    db_session.add_all(txns)
    await db_session.commit()

    specs = load_category_specs(categories_yaml)
    await apply_categories(db_session, specs, apply_changes=True)

    summary = await run_reclassify_job(db_session)

    assert summary.total_count == 3
    assert summary.classified_count == 3

    await db_session.refresh(txns[0])
    await db_session.refresh(txns[1])
    await db_session.refresh(txns[2])

    assert txns[0].category == "餐飲"
    assert txns[1].category == "超商"
    assert txns[2].category == "未分類"


async def test_reclassify_without_seed_leaves_uncategorized(db_session) -> None:
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=500,
        due_date=date(2026, 4, 15),
    )
    db_session.add(bill)
    await db_session.flush()

    txn = Transaction(
        bill_id=bill.id,
        trans_date=date(2026, 3, 1),
        merchant="麥當勞",
        amount=150,
        category=None,
    )
    db_session.add(txn)
    await db_session.commit()

    summary = await run_reclassify_job(db_session)

    assert summary.classified_count == 1
    await db_session.refresh(txn)
    assert txn.category == "未分類"
