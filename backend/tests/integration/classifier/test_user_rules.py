"""UserRuleMatcher 整合與單元測試。

bills-management-and-insights §2.2-§2.3 + audit P2 ``classify-regex-perf-and-redos``：
- 三種 pattern_type（keyword / exact / regex）的命中與邊界
- regex 編譯錯誤 fail-soft（視為 not match，不拋例外）
- regex 比對改為**同步**：移除每筆交易的 ``run_in_executor`` dispatch
- ReDoS 防護移至 ``load()`` 期 burn-in：catastrophic pattern 於載入時停用該規則，
  per-transaction 路徑因此不再有 timeout 開銷
- empty rules → None；priority DESC + id ASC 排序
- ``load(session)`` 從 DB 載入 enabled rules（disabled 不入 snapshot）
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier import user_rules
from ccas.classifier.user_rules import (
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

    async def test_regex_compile_error_fail_soft(self, caplog) -> None:
        """無效 regex 視為 not match，log warning，不拋例外。"""
        matcher = UserRuleMatcher(
            [_make_rule(r"[unclosed", PatternType.REGEX, category="x")]
        )
        with caplog.at_level("WARNING", logger="ccas.classifier.user_rules"):
            result = await matcher.match("test")
        assert result is None
        assert any("regex pattern error" in r.message for r in caplog.records)


class TestSyncMatching:
    """效能：per-transaction 比對不再 dispatch 至 executor（改同步），

    但對外 ``match()`` 介面維持 ``async def`` 以不破壞呼叫端契約。
    """

    def test_internal_matchers_are_synchronous(self) -> None:
        assert not inspect.iscoroutinefunction(UserRuleMatcher._matches)
        assert not inspect.iscoroutinefunction(UserRuleMatcher._regex_match)

    async def test_match_remains_async_for_callers(self) -> None:
        assert inspect.iscoroutinefunction(UserRuleMatcher.match)
        matcher = UserRuleMatcher([_make_rule("星巴克", PatternType.KEYWORD)])
        assert await matcher.match("星巴克信義店") == "餐飲"

    async def test_safe_regex_matches_without_executor(self, monkeypatch) -> None:
        """確認安全 regex 走同步路徑，不依賴 event loop 的 executor。"""

        def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("run_in_executor must not be called per-transaction")

        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "run_in_executor", _boom)

        matcher = UserRuleMatcher(
            [_make_rule(r"^7-?eleven", PatternType.REGEX, category="便利商店")]
        )
        assert await matcher.match("7-Eleven") == "便利商店"


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


class TestLoadTimeBurnIn:
    """ReDoS 防護移至 load 期：catastrophic regex 於載入時 burn-in 失敗即停用。

    取代舊版每筆交易的 ``asyncio.wait_for`` timeout：load 期對每個編譯成功的
    regex 以惡意短字串燒烤一次，逾時即視為不安全並排除該規則，per-transaction
    路徑因此可改為同步、零 timeout 開銷。
    """

    async def _seed(self, session: AsyncSession, regex_pattern: str) -> None:
        risk = Category(keyword="r", category="風險")
        safe = Category(keyword="s", category="安全")
        session.add_all([risk, safe])
        await session.flush()
        session.add_all(
            [
                UserClassificationRule(
                    pattern=regex_pattern,
                    pattern_type=PatternType.REGEX,
                    category_id=risk.id,
                    priority=20,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="安全商店",
                    pattern_type=PatternType.KEYWORD,
                    category_id=safe.id,
                    priority=10,
                    enabled=True,
                ),
            ]
        )
        await session.flush()

    async def test_catastrophic_regex_disabled_at_load(
        self, db_session: AsyncSession, monkeypatch, caplog
    ) -> None:
        def slow_search(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
            time.sleep(0.5)
            return None

        monkeypatch.setattr(user_rules, "_re_search", slow_search)
        monkeypatch.setattr(user_rules, "REGEX_BURN_IN_TIMEOUT_SECONDS", 0.05)

        await self._seed(db_session, r"(a+)+$")

        with caplog.at_level("WARNING", logger="ccas.classifier.user_rules"):
            matcher = await UserRuleMatcher.load(db_session)

        # catastrophic regex 被停用，只剩 keyword 規則
        assert matcher.count == 1
        assert await matcher.match("安全商店分店") == "安全"
        assert any("burn-in" in r.message.lower() for r in caplog.records)

    async def test_safe_regex_survives_load(self, db_session: AsyncSession) -> None:
        await self._seed(db_session, r"^7-?eleven")
        matcher = await UserRuleMatcher.load(db_session)
        assert matcher.count == 2
        assert await matcher.match("7eleven 門市") == "風險"

    async def test_alternation_bomb_caught_by_mixed_char_probes(
        self, db_session: AsyncSession, monkeypatch, caplog
    ) -> None:
        """ambiguous alternation（``(a|b|ab)+``）只在「多字元交錯」輸入才分歧爆炸。

        單字元探測（``"a"*64``、``"0"*64``）抓不到此類，必須靠 ``"ab"`` / ``"abc"``
        重複探測。以只對含 ``"ab"`` 的探測變慢的假 search 驗證：唯有混合字元探測
        存在，load 期才會偵測到並停用該規則（移除這些探測時本測試會失敗）。
        """

        def selective_slow(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
            if "ab" in text:
                time.sleep(0.5)
            return None

        monkeypatch.setattr(user_rules, "_re_search", selective_slow)
        monkeypatch.setattr(user_rules, "REGEX_BURN_IN_TIMEOUT_SECONDS", 0.05)

        await self._seed(db_session, r"(a|b|ab)+$")

        with caplog.at_level("WARNING", logger="ccas.classifier.user_rules"):
            matcher = await UserRuleMatcher.load(db_session)

        # 混合字元探測偵測到回溯爆炸 → 停用該 regex，只剩 keyword 規則
        assert matcher.count == 1
        assert await matcher.match("安全商店分店") == "安全"
        assert any("burn-in" in r.message.lower() for r in caplog.records)
