"""分類判定（Category decision）：以真實規則驗證判定順序。

手動分類覆寫 → 分類規則（priority 高者先、相同 priority 依 id）→ 內建關鍵字規則
→ 預設消費類別；以原始商家名稱比對，商家別名不影響判定。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.classifier import CategoryDecision, Classifier, DecisionSource
from ccas.constants import DEFAULT_CATEGORY
from ccas.storage.models import (
    Base,
    Category,
    PatternType,
    Transaction,
    UserClassificationRule,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _keyword(session: AsyncSession, keyword: str, category: str) -> Category:
    row = Category(keyword=keyword, category=category)
    session.add(row)
    await session.flush()
    return row


async def _user_rule(
    session: AsyncSession,
    pattern: str,
    category: Category,
    *,
    priority: int = 0,
    enabled: bool = True,
) -> None:
    session.add(
        UserClassificationRule(
            pattern=pattern,
            pattern_type=PatternType.KEYWORD,
            category_id=category.id,
            priority=priority,
            enabled=enabled,
        )
    )
    await session.flush()


def _txn(merchant: str, *, override: bool = False, alias: str = "") -> Transaction:
    return Transaction(
        merchant=merchant, manual_category_override=override, merchant_alias=alias
    )


async def _decide(session: AsyncSession, txn: Transaction) -> CategoryDecision:
    await session.commit()
    classifier = await Classifier.load(session)
    return await classifier.decide(txn)


async def test_manual_override_keeps_existing_category(session: AsyncSession):
    dining = await _keyword(session, "UBER", "交通")
    await _user_rule(session, "UBER", dining)

    decision = await _decide(session, _txn("UBER EATS", override=True))

    assert decision == CategoryDecision(None, DecisionSource.MANUAL_OVERRIDE)


async def test_user_rule_beats_keyword(session: AsyncSession):
    await _keyword(session, "UBER", "交通")
    dining = await _keyword(session, "餐廳", "餐飲")
    await _user_rule(session, "UBER", dining)

    decision = await _decide(session, _txn("UBER EATS"))

    assert decision == CategoryDecision("餐飲", DecisionSource.USER_RULE)


async def test_higher_priority_user_rule_wins(session: AsyncSession):
    dining = await _keyword(session, "餐廳", "餐飲")
    transport = await _keyword(session, "捷運", "交通")
    await _user_rule(session, "UBER", transport, priority=50)
    await _user_rule(session, "UBER", dining, priority=100)

    decision = await _decide(session, _txn("UBER EATS"))

    assert decision == CategoryDecision("餐飲", DecisionSource.USER_RULE)


async def test_disabled_user_rule_is_skipped(session: AsyncSession):
    await _keyword(session, "UBER", "交通")
    dining = await _keyword(session, "餐廳", "餐飲")
    await _user_rule(session, "UBER", dining, enabled=False)

    decision = await _decide(session, _txn("UBER EATS"))

    assert decision == CategoryDecision("交通", DecisionSource.KEYWORD)


async def test_keyword_when_no_user_rule_matches(session: AsyncSession):
    await _keyword(session, "7-ELEVEN", "便利商店")

    decision = await _decide(session, _txn("7-ELEVEN 台北"))

    assert decision == CategoryDecision("便利商店", DecisionSource.KEYWORD)


async def test_default_when_nothing_matches(session: AsyncSession):
    await _keyword(session, "7-ELEVEN", "便利商店")

    decision = await _decide(session, _txn("UNKNOWN SHOP"))

    assert decision == CategoryDecision(DEFAULT_CATEGORY, DecisionSource.DEFAULT)


async def test_merchant_alias_is_ignored(session: AsyncSession):
    dining = await _keyword(session, "餐廳", "餐飲")
    await _user_rule(session, "MY CAFE", dining)

    decision = await _decide(session, _txn("SQ *X1234", alias="MY CAFE"))

    assert decision == CategoryDecision(DEFAULT_CATEGORY, DecisionSource.DEFAULT)


async def test_load_reflects_current_rules(session: AsyncSession):
    first = await _decide(session, _txn("FAMILYMART"))
    await _keyword(session, "FAMILYMART", "便利商店")
    second = await _decide(session, _txn("FAMILYMART"))

    assert first.source is DecisionSource.DEFAULT
    assert second == CategoryDecision("便利商店", DecisionSource.KEYWORD)
