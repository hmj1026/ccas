"""user_rules 模組的單元測試。

涵蓋 module-level helper（_compile_pattern / _re_search /
_pattern_survives_burn_in）、UserRule snapshot、UserRuleMatcher.match 的三種
pattern_type 比對，以及 UserRuleMatcher.load() 的 DB 載入 / 排序 / enabled 過濾 /
REGEX 預編譯 / burn-in 停用流程。

load() 與比對皆以 in-memory SQLite + 真實 ORM model 驅動，讓 SQL 實際執行。
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.classifier import user_rules
from ccas.classifier.user_rules import (
    UserRule,
    UserRuleMatcher,
    _compile_pattern,
    _pattern_survives_burn_in,
    _re_search,
)
from ccas.storage.models import (
    Base,
    Category,
    PatternType,
    UserClassificationRule,
)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_category(session: AsyncSession, category: str) -> int:
    row = Category(keyword=category, category=category)
    session.add(row)
    await session.commit()
    return row.id


async def _add_rule(
    session: AsyncSession,
    *,
    pattern: str,
    pattern_type: PatternType,
    category_id: int,
    priority: int = 0,
    enabled: bool = True,
) -> UserClassificationRule:
    rule = UserClassificationRule(
        pattern=pattern,
        pattern_type=pattern_type,
        category_id=category_id,
        priority=priority,
        enabled=enabled,
    )
    session.add(rule)
    await session.commit()
    return rule


class TestCompilePattern:
    def test_regex_valid_returns_pattern(self) -> None:
        compiled = _compile_pattern(r"star.*", PatternType.REGEX)
        assert compiled is not None
        assert compiled.search("starbucks") is not None

    def test_regex_invalid_returns_none(self) -> None:
        # 未閉合 group → re.error → fail-soft None。
        assert _compile_pattern(r"(", PatternType.REGEX) is None

    def test_non_regex_returns_none(self) -> None:
        assert _compile_pattern("starbucks", PatternType.KEYWORD) is None
        assert _compile_pattern("starbucks", PatternType.EXACT) is None


class TestReSearch:
    def test_match(self) -> None:
        compiled = re.compile(r"star")
        assert _re_search(compiled, "starbucks") is not None

    def test_no_match(self) -> None:
        compiled = re.compile(r"^zzz$")
        assert _re_search(compiled, "starbucks") is None


class TestPatternSurvivesBurnIn:
    async def test_safe_pattern_survives(self) -> None:
        compiled = re.compile(r"abc")
        assert await _pattern_survives_burn_in(compiled) is True

    async def test_timeout_marks_as_unsafe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 不依賴真實 catastrophic regex：以慢速 _re_search + 極短 timeout
        # 觸發 TimeoutError，使 burn-in 回傳 False（deterministic、快速）。
        def _slow(_pattern: re.Pattern[str], _text: str) -> None:
            time.sleep(0.2)
            return None

        monkeypatch.setattr(user_rules, "_re_search", _slow)
        monkeypatch.setattr(user_rules, "REGEX_BURN_IN_TIMEOUT_SECONDS", 0.02)

        compiled = re.compile(r"abc")
        assert await _pattern_survives_burn_in(compiled) is False


class TestUserRule:
    def test_fields_and_defaults(self) -> None:
        rule = UserRule(
            id=1,
            pattern="星巴克",
            pattern_type=PatternType.KEYWORD,
            category_name="餐飲",
            priority=5,
        )
        assert rule.id == 1
        assert rule.pattern == "星巴克"
        assert rule.pattern_type == PatternType.KEYWORD
        assert rule.category_name == "餐飲"
        assert rule.priority == 5
        assert rule.compiled_pattern is None

    def test_frozen(self) -> None:
        rule = UserRule(
            id=1,
            pattern="星巴克",
            pattern_type=PatternType.KEYWORD,
            category_name="餐飲",
            priority=0,
        )
        with pytest.raises(AttributeError):
            rule.pattern = "other"  # type: ignore[misc]


def _make_rule(
    *,
    pattern: str,
    pattern_type: PatternType,
    category_name: str = "餐飲",
    priority: int = 0,
    compiled: re.Pattern[str] | None = None,
) -> UserRule:
    return UserRule(
        id=1,
        pattern=pattern,
        pattern_type=pattern_type,
        category_name=category_name,
        priority=priority,
        compiled_pattern=compiled,
    )


class TestUserRuleMatcherMatch:
    async def test_empty_matcher_returns_none(self) -> None:
        matcher = UserRuleMatcher([])
        assert matcher.count == 0
        assert await matcher.match("星巴克") is None

    async def test_keyword_substring_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(pattern="STARBUCKS", pattern_type=PatternType.KEYWORD)]
        )
        # normalize 後 case-insensitive 子字串比對。
        assert await matcher.match("My Starbucks Coffee") == "餐飲"

    async def test_keyword_no_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(pattern="星巴克", pattern_type=PatternType.KEYWORD)]
        )
        assert await matcher.match("家樂福") is None

    async def test_exact_match(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(pattern="Starbucks", pattern_type=PatternType.EXACT)]
        )
        assert await matcher.match("starbucks") == "餐飲"

    async def test_exact_no_match_on_substring(self) -> None:
        matcher = UserRuleMatcher(
            [_make_rule(pattern="star", pattern_type=PatternType.EXACT)]
        )
        assert await matcher.match("starbucks") is None

    async def test_regex_match_with_precompiled(self) -> None:
        compiled = re.compile(r"star.*bucks")
        matcher = UserRuleMatcher(
            [
                _make_rule(
                    pattern=r"star.*bucks",
                    pattern_type=PatternType.REGEX,
                    compiled=compiled,
                )
            ]
        )
        assert await matcher.match("starbucks") == "餐飲"

    async def test_regex_match_recompiles_when_not_precompiled(self) -> None:
        # compiled_pattern=None → _regex_match fail-soft 編譯一次。
        matcher = UserRuleMatcher(
            [_make_rule(pattern=r"star", pattern_type=PatternType.REGEX)]
        )
        assert await matcher.match("starbucks") == "餐飲"

    async def test_regex_invalid_recompile_returns_no_match(self) -> None:
        # 無效 regex 且未預編譯 → 重新編譯失敗 → 視為 not match。
        matcher = UserRuleMatcher(
            [_make_rule(pattern=r"(", pattern_type=PatternType.REGEX)]
        )
        assert await matcher.match("starbucks") is None

    async def test_first_matching_rule_wins(self) -> None:
        matcher = UserRuleMatcher(
            [
                _make_rule(
                    pattern="star",
                    pattern_type=PatternType.KEYWORD,
                    category_name="第一",
                ),
                _make_rule(
                    pattern="star",
                    pattern_type=PatternType.KEYWORD,
                    category_name="第二",
                ),
            ]
        )
        assert await matcher.match("starbucks") == "第一"

    async def test_unknown_pattern_type_never_matches(self) -> None:
        # 防禦性分支：pattern_type 非三種 enum 之一時 _matches 回 False。
        rule = UserRule(
            id=1,
            pattern="star",
            pattern_type="unknown",  # type: ignore[arg-type]
            category_name="餐飲",
            priority=0,
        )
        matcher = UserRuleMatcher([rule])
        assert await matcher.match("starbucks") is None


class TestUserRuleMatcherLoad:
    async def test_empty_table(self, session: AsyncSession) -> None:
        matcher = await UserRuleMatcher.load(session)
        assert matcher.count == 0

    async def test_loads_enabled_keyword_rule_with_category_name(
        self, session: AsyncSession
    ) -> None:
        cat_id = await _add_category(session, "餐飲")
        await _add_rule(
            session,
            pattern="星巴克",
            pattern_type=PatternType.KEYWORD,
            category_id=cat_id,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 1
        assert await matcher.match("星巴克門市") == "餐飲"

    async def test_excludes_disabled_rules(self, session: AsyncSession) -> None:
        cat_id = await _add_category(session, "餐飲")
        await _add_rule(
            session,
            pattern="星巴克",
            pattern_type=PatternType.KEYWORD,
            category_id=cat_id,
            enabled=False,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 0

    async def test_ordered_by_priority_desc_then_id_asc(
        self, session: AsyncSession
    ) -> None:
        low = await _add_category(session, "低優先")
        high = await _add_category(session, "高優先")
        # 兩條 pattern 同樣命中 "star"；高 priority 應先比中。
        await _add_rule(
            session,
            pattern="star",
            pattern_type=PatternType.KEYWORD,
            category_id=low,
            priority=1,
        )
        await _add_rule(
            session,
            pattern="star",
            pattern_type=PatternType.KEYWORD,
            category_id=high,
            priority=10,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 2
        assert await matcher.match("starbucks") == "高優先"

    async def test_valid_regex_rule_loaded_and_precompiled(
        self, session: AsyncSession
    ) -> None:
        cat_id = await _add_category(session, "餐飲")
        await _add_rule(
            session,
            pattern=r"star.*bucks",
            pattern_type=PatternType.REGEX,
            category_id=cat_id,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 1
        assert await matcher.match("starbucks") == "餐飲"

    async def test_invalid_regex_rule_still_loaded_failsoft(
        self, session: AsyncSession
    ) -> None:
        # 無效 regex 於 load 期編譯失敗（compiled None），不被 burn-in 停用，
        # 仍進 snapshot；比對時 fail-soft 視為 not match。
        cat_id = await _add_category(session, "餐飲")
        await _add_rule(
            session,
            pattern=r"(",
            pattern_type=PatternType.REGEX,
            category_id=cat_id,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 1
        assert await matcher.match("starbucks") is None

    async def test_regex_failing_burn_in_is_disabled(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 以 monkeypatch 讓 burn-in 一律失敗，驗證 catastrophic regex
        # 會被排除於 snapshot 外（load 的 disable 分支）。
        async def _always_unsafe(_compiled: re.Pattern[str]) -> bool:
            return False

        monkeypatch.setattr(user_rules, "_pattern_survives_burn_in", _always_unsafe)

        cat_id = await _add_category(session, "餐飲")
        await _add_rule(
            session,
            pattern=r"star.*",
            pattern_type=PatternType.REGEX,
            category_id=cat_id,
        )

        matcher = await UserRuleMatcher.load(session)

        assert matcher.count == 0
