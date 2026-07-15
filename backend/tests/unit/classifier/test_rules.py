"""rules 模組的單元測試。

測試 ClassificationRule、RuleSet 與 load_rules() 的行為。
load_rules() 以 in-memory SQLite + 真實 Category model 驅動，讓 SQL 實際執行。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.classifier.rules import ClassificationRule, RuleSet, load_rules
from ccas.storage.models import Base, Category


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_category(
    session: AsyncSession, *, keyword: str, category: str
) -> Category:
    row = Category(keyword=keyword, category=category)
    session.add(row)
    await session.commit()
    return row


class TestClassificationRule:
    def test_frozen_dataclass(self) -> None:
        rule = ClassificationRule(rule_id=1, keyword="星巴克", category="餐飲")
        assert rule.rule_id == 1
        assert rule.keyword == "星巴克"
        assert rule.category == "餐飲"

    def test_immutability(self) -> None:
        rule = ClassificationRule(rule_id=1, keyword="星巴克", category="餐飲")
        try:
            rule.keyword = "other"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass


class TestRuleSet:
    def test_empty_rule_set(self) -> None:
        rs = RuleSet(rules=())
        assert rs.count == 0

    def test_rule_set_count(self) -> None:
        rules = (
            ClassificationRule(rule_id=1, keyword="星巴克", category="餐飲"),
            ClassificationRule(rule_id=2, keyword="台灣大", category="通訊"),
        )
        rs = RuleSet(rules=rules)
        assert rs.count == 2

    def test_rule_set_immutability(self) -> None:
        rs = RuleSet(rules=())
        try:
            rs.rules = ()  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass

    def test_reload_returns_new_instance(self) -> None:
        """重載等同於建立新 RuleSet — 舊實例不變。"""
        old = RuleSet(
            rules=(ClassificationRule(rule_id=1, keyword="星巴克", category="餐飲"),)
        )
        new = RuleSet(
            rules=(
                ClassificationRule(rule_id=1, keyword="星巴克", category="餐飲"),
                ClassificationRule(rule_id=2, keyword="台灣大", category="通訊"),
            )
        )
        assert old.count == 1
        assert new.count == 2


class TestLoadRules:
    async def test_empty_table_returns_empty_ruleset(
        self, session: AsyncSession
    ) -> None:
        rule_set = await load_rules(session)
        assert rule_set.count == 0
        assert rule_set.rules == ()

    async def test_maps_columns_to_rule_fields(self, session: AsyncSession) -> None:
        row = await _add_category(session, keyword="星巴克", category="餐飲")

        rule_set = await load_rules(session)

        assert rule_set.count == 1
        rule = rule_set.rules[0]
        assert isinstance(rule, ClassificationRule)
        assert rule.rule_id == row.id
        assert rule.keyword == "星巴克"
        assert rule.category == "餐飲"

    async def test_ordered_by_id_ascending(self, session: AsyncSession) -> None:
        await _add_category(session, keyword="星巴克", category="餐飲")
        await _add_category(session, keyword="台灣大", category="通訊")
        await _add_category(session, keyword="家樂福", category="購物")

        rule_set = await load_rules(session)

        ids = [r.rule_id for r in rule_set.rules]
        keywords = [r.keyword for r in rule_set.rules]
        assert ids == sorted(ids)
        assert keywords == ["星巴克", "台灣大", "家樂福"]

    async def test_returns_immutable_snapshot(self, session: AsyncSession) -> None:
        await _add_category(session, keyword="星巴克", category="餐飲")

        rule_set = await load_rules(session)

        assert isinstance(rule_set.rules, tuple)
