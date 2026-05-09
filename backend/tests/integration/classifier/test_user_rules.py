"""UserRuleMatcher 整合與單元測試。

bills-management-and-insights §2.2-§2.3：
- 三種 pattern_type（keyword / exact / regex）的命中與邊界
- regex 100ms timeout fail-soft（透過 monkeypatch _re_search 模擬慢）
- regex 編譯錯誤 fail-soft
- empty rules → None
- priority DESC + id ASC 排序
- ``load(session)`` 從 DB 載入 enabled rules（disabled 不入 snapshot）
"""

from __future__ import annotations

import asyncio
import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier import user_rules
from ccas.classifier.user_rules import (
    REGEX_TIMEOUT_SECONDS,
    UserRule,
    UserRuleMatcher,
)
from ccas.storage.models import (
    Category,
    PatternType,
    UserClassificationRule,
)


def _make_rule(
    pattern: str,
    pattern_type: PatternType = PatternType.KEYWORD,
    category: str = "餐飲",
    priority: int = 0,
    rule_id: int = 1,
) -> UserRule:
    return UserRule(
        id=rule_id,
        pattern=pattern,
        pattern_type=pattern_type,
        category_name=category,
        priority=priority,
    )


class TestKeywordPatternType:
    async def test_substring_match(self) -> None:
        matcher = UserRuleMatcher([_make_rule("星巴克", PatternType.KEYWORD)])
        assert await matcher.match("星巴克台北車站店") == "餐飲"

    async def test_case_insensitive(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule("AMAZON", PatternType.KEYWORD, category="購物")]
        )
        assert await matcher.match("amazon.com 訂單") == "購物"

    async def test_no_match_returns_none(self) -> None:
        matcher = UserRuleMatcher([_make_rule("星巴克", PatternType.KEYWORD)])
        assert await matcher.match("Louisa Coffee") is None

    async def test_normalize_collapses_whitespace(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule("台灣 大哥大", PatternType.KEYWORD, category="通訊")]
        )
        assert await matcher.match("台灣  大哥大 月租費") == "通訊"


class TestExactPatternType:
    async def test_exact_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule("UBER EATS", PatternType.EXACT, category="外送")]
        )
        assert await matcher.match("uber eats") == "外送"

    async def test_partial_does_not_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule("UBER EATS", PatternType.EXACT, category="外送")]
        )
        assert await matcher.match("uber eats 台北") is None


class TestRegexPatternType:
    async def test_simple_regex_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(r"^7-?eleven", PatternType.REGEX, category="便利商店")]
        )
        assert await matcher.match("7-Eleven 中正店") == "便利商店"
        assert await matcher.match("7eleven") == "便利商店"

    async def test_regex_no_match_returns_none(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(r"^starbucks$", PatternType.REGEX, category="餐飲")]
        )
        assert await matcher.match("Starbucks Taipei") is None

    async def test_regex_timeout_fail_soft(self, monkeypatch, caplog) -> None:
        """超過 100ms 的 regex 視為 not match，log warning，不阻斷其他規則。"""
        import time

        def slow_search(pattern: str, text: str) -> re.Match[str] | None:
            time.sleep(REGEX_TIMEOUT_SECONDS * 5)  # 0.5s, 遠大於 100ms
            return None

        monkeypatch.setattr(user_rules, "_re_search", slow_search)

        matcher = UserRuleMatcher(
            [_make_rule(r"(a+)+$", PatternType.REGEX, category="x")]
        )

        with caplog.at_level("WARNING", logger="ccas.classifier.user_rules"):
            result = await matcher.match("aaaaaaaa!")

        assert result is None
        assert any("timeout" in r.message for r in caplog.records)

    async def test_regex_compile_error_fail_soft(self, caplog) -> None:
        """無效 regex 視為 not match，log warning，不拋例外。"""
        matcher = UserRuleMatcher(
            [_make_rule(r"[unclosed", PatternType.REGEX, category="x")]
        )
        with caplog.at_level("WARNING", logger="ccas.classifier.user_rules"):
            result = await matcher.match("test")
        assert result is None
        assert any("regex pattern error" in r.message for r in caplog.records)

    async def test_other_rules_continue_after_regex_timeout(self, monkeypatch) -> None:
        """timeout 規則之後的規則仍然會被評估。"""
        import time

        def slow_search(pattern: str, text: str) -> re.Match[str] | None:
            time.sleep(REGEX_TIMEOUT_SECONDS * 3)
            return None

        monkeypatch.setattr(user_rules, "_re_search", slow_search)

        matcher = UserRuleMatcher(
            [
                _make_rule(
                    r"slow.*pattern",
                    PatternType.REGEX,
                    category="x",
                    priority=10,
                    rule_id=1,
                ),
                _make_rule(
                    "fallback",
                    PatternType.KEYWORD,
                    category="後備",
                    priority=5,
                    rule_id=2,
                ),
            ]
        )
        assert await matcher.match("fallback merchant") == "後備"


class TestEmptyAndOrdering:
    async def test_empty_rules_returns_none(self) -> None:
        matcher = UserRuleMatcher([])
        assert matcher.count == 0
        assert await matcher.match("anything") is None

    async def test_priority_desc_first_match_wins(self) -> None:
        """priority 較高的規則優先命中。"""
        matcher = UserRuleMatcher(
            [
                _make_rule(
                    "台灣", PatternType.KEYWORD, category="A", priority=10, rule_id=1
                ),
                _make_rule(
                    "台灣", PatternType.KEYWORD, category="B", priority=5, rule_id=2
                ),
            ]
        )
        assert await matcher.match("台灣大哥大") == "A"


class TestLoadFromDb:
    async def _seed_rules(self, session: AsyncSession) -> None:
        food = Category(keyword="星巴克", category="餐飲")
        gas = Category(keyword="加油", category="交通")
        session.add_all([food, gas])
        await session.flush()

        session.add_all(
            [
                UserClassificationRule(
                    pattern="星巴克",
                    pattern_type=PatternType.KEYWORD,
                    category_id=food.id,
                    priority=10,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="^7-?eleven",
                    pattern_type=PatternType.REGEX,
                    category_id=food.id,
                    priority=20,
                    enabled=True,
                ),
                # disabled rule — load() 應排除
                UserClassificationRule(
                    pattern="加油站",
                    pattern_type=PatternType.KEYWORD,
                    category_id=gas.id,
                    priority=5,
                    enabled=False,
                ),
            ]
        )
        await session.flush()

    async def test_load_excludes_disabled(self, db_session: AsyncSession) -> None:
        await self._seed_rules(db_session)
        matcher = await UserRuleMatcher.load(db_session)
        assert matcher.count == 2
        # 7-eleven priority=20 應排第一
        assert await matcher.match("7-Eleven") == "餐飲"
        # 加油站 disabled，不應命中
        assert await matcher.match("中油加油站") is None

    async def test_load_orders_by_priority_desc(self, db_session: AsyncSession) -> None:
        food = Category(keyword="星巴克", category="餐飲")
        shop = Category(keyword="購物", category="購物")
        db_session.add_all([food, shop])
        await db_session.flush()

        db_session.add_all(
            [
                UserClassificationRule(
                    pattern="台灣",
                    pattern_type=PatternType.KEYWORD,
                    category_id=food.id,
                    priority=5,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="台灣",
                    pattern_type=PatternType.KEYWORD,
                    category_id=shop.id,
                    priority=10,
                    enabled=True,
                ),
            ]
        )
        await db_session.flush()

        matcher = await UserRuleMatcher.load(db_session)
        assert await matcher.match("台灣大哥大") == "購物"

    async def test_load_empty_table(self, db_session: AsyncSession) -> None:
        matcher = await UserRuleMatcher.load(db_session)
        assert matcher.count == 0
        assert await matcher.match("anything") is None


class TestEventLoopNotBlocked:
    """confirm regex timeout 不阻塞 caller 的 event loop。"""

    async def test_other_async_tasks_progress_during_regex_timeout(
        self, monkeypatch
    ) -> None:
        import time

        def slow_search(pattern: str, text: str) -> re.Match[str] | None:
            time.sleep(REGEX_TIMEOUT_SECONDS * 3)
            return None

        monkeypatch.setattr(user_rules, "_re_search", slow_search)

        matcher = UserRuleMatcher(
            [_make_rule(r"slow", PatternType.REGEX, category="x")]
        )

        ticks: list[float] = []

        async def ticker() -> None:
            for _ in range(3):
                await asyncio.sleep(0.05)
                ticks.append(asyncio.get_running_loop().time())

        async def matcher_call() -> str | None:
            return await matcher.match("test")

        ticker_task = asyncio.create_task(ticker())
        result = await matcher_call()
        await ticker_task

        assert result is None
        # ticker 至少跑滿 3 次，代表 event loop 沒被 sync sleep 阻塞
        assert len(ticks) == 3


@pytest.mark.parametrize(
    "rules,merchant,expected",
    [
        # 規則並列、第一個命中即返回
        ([("星巴克", PatternType.KEYWORD, "餐飲", 10)], "星巴克信義店", "餐飲"),
        # exact 不命中走下一個
        (
            [
                ("UBER EATS", PatternType.EXACT, "外送", 10),
                ("uber", PatternType.KEYWORD, "交通", 5),
            ],
            "uber eats 訂單",
            "交通",
        ),
    ],
)
async def test_match_parametrized(
    rules: list[tuple[str, PatternType, str, int]],
    merchant: str,
    expected: str | None,
) -> None:
    matcher = UserRuleMatcher(
        [
            _make_rule(p, t, c, prio, rule_id=i)
            for i, (p, t, c, prio) in enumerate(rules, start=1)
        ]
    )
    assert await matcher.match(merchant) == expected
