"""使用者自訂進階分類規則 matcher（bills-management-and-insights §2）。

從 ``classification_rules`` 表載入 enabled 規則 snapshot，依 priority DESC、
id ASC 排序，逐筆比對 transaction merchant。支援三種 pattern_type：

- ``keyword``：normalize 後子字串比對（與既有 engine 同邏輯）
- ``exact``：normalize 後完全相等
- ``regex``：預編譯後 ``Pattern.search``，同步比對；編譯錯誤 fail-soft（log
  warning + 視為 not match），不阻斷其他規則。

設計（audit P2 ``classify-regex-perf-and-redos``）：
- ``UserRuleMatcher.load(session)`` 一次性 query 規則 + 對應 category 名，
  避免 N+1 查詢；之後對每筆 transaction 走 in-memory snapshot
- **效能**：per-transaction 比對全程同步（KEYWORD/EXACT/REGEX 皆然），不再
  對每筆交易 dispatch 至 ``run_in_executor`` / 包 ``asyncio.wait_for``，移除
  每筆交易的 executor 開銷
- **ReDoS 防護移至 load 期**：REGEX 規則於 ``load()`` 時 ``re.compile`` 一次並
  以惡意短字串做一次性 burn-in（``asyncio.wait_for`` + executor，
  ``REGEX_BURN_IN_TIMEOUT_SECONDS`` 逾時）；逾時的 catastrophic pattern 會被
  停用（排除於 snapshot），確保同步比對不被惡意 regex 阻塞。API 層
  （``schemas.py`` 的 model_validator）另在規則建立時即拒收 nested-quantifier
  pattern，與前端 ``detectComplexRegex`` 啟發式維持 SSOT
- ``_re_search`` 抽出為 module-level 函式以利測試 monkeypatch
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier.engine import normalize
from ccas.storage.models import (
    Category,
    PatternType,
    UserClassificationRule,
)

logger = logging.getLogger(__name__)

# Load 期 ReDoS burn-in 的 per-probe timeout。per-transaction 路徑已改同步、無
# timeout 開銷；catastrophic pattern 在 load() 一次性燒烤時即被偵測並停用。
REGEX_BURN_IN_TIMEOUT_SECONDS: float = 0.5

# 公認會觸發 catastrophic backtracking 的惡意短字串（針對 (a+)+、(\d+)+、
# (\w+)+、(a|aa)+ 等經典 nested quantifier / alternation）。安全 pattern 在微秒內
# 完成，不受影響。含空白者模擬真實商戶名（merchant 多含空白／斜線）。
#
# 單字元探測（"a"*64 等）只能引爆 inner-quantifier 類；ambiguous alternation 類
# （如 ``(a|b|ab)+``）需要「多種字元交錯」才會分歧爆炸，故加入 "ab"／"abc" 重複探測，
# 覆蓋 schemas._NESTED_QUANTIFIER_RE 啟發式可能漏接、但實際會 hang 的交替 pattern。
_BURN_IN_PROBES: tuple[str, ...] = (
    "a" * 64 + "!",
    "0" * 64 + "!",
    "a0" * 32 + "!",
    "a" * 40 + " " * 16 + "!",
    "ab" * 32 + "!",
    "abc" * 21 + "!",
)


def _re_search(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """已編譯 regex 的 ``search`` 薄包裝，作為測試 monkeypatch 的注入點。"""
    return pattern.search(text)


async def _pattern_survives_burn_in(compiled: re.Pattern[str]) -> bool:
    """以惡意短字串燒烤已編譯 regex；任一探測逾時即視為 ReDoS 風險（False）。

    僅在 ``load()``（async context）一次性執行。逾時的 executor thread 雖無法
    強制中止（Python thread 無法 kill），但只在載入時短暫洩漏直到 ``re.search``
    自然返回；per-transaction 路徑完全無此開銷。
    """
    loop = asyncio.get_running_loop()
    for probe in _BURN_IN_PROBES:
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, _re_search, compiled, probe),
                timeout=REGEX_BURN_IN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return False
    return True


def _compile_pattern(pattern: str, pattern_type: PatternType) -> re.Pattern[str] | None:
    """對 REGEX 規則預編譯；無效 regex 回傳 ``None``（fail-soft），

    非 REGEX 規則一律回傳 ``None``。編譯錯誤 log warning 後視為「無此規則」，
    在 ``_regex_match`` 內會被當成 not match，與既有 fail-soft 行為一致。
    """
    if pattern_type != PatternType.REGEX:
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        logger.warning(
            "regex pattern error, treating as no match",
            extra={"pattern": pattern, "error": str(exc)},
        )
        return None


@dataclass(frozen=True)
class UserRule:
    """In-memory snapshot of a single user classification rule.

    與 ``UserClassificationRule`` ORM model 解耦，避免 detached instance 問題。
    ``category_name`` 為 JOIN ``categories.category`` 後的字串值。

    ``compiled_pattern`` 在 ``load()`` 時對 REGEX 規則預編譯一次，避免每筆
    transaction 重複 ``re.compile`` / 依賴 ``re`` 模組的小型 LRU 快取；非 REGEX
    規則為 ``None``。``re.Pattern`` 不可 pickle，但本 snapshot 僅存在於單次
    ``load()`` 的記憶體中、不會被序列化，因此無影響。
    """

    id: int
    pattern: str
    pattern_type: PatternType
    category_name: str
    priority: int
    compiled_pattern: re.Pattern[str] | None = None


class UserRuleMatcher:
    """Match transaction merchant against user-defined classification rules.

    建構時接受規則 snapshot tuple；典型透過 ``UserRuleMatcher.load(session)``
    從 DB 一次性載入 enabled 規則。對每筆 transaction 呼叫 ``match(merchant)``
    回傳第一個命中規則的 category 名稱（或 None）。
    """

    def __init__(self, rules: Sequence[UserRule]):
        self._rules: tuple[UserRule, ...] = tuple(rules)

    @classmethod
    async def load(cls, session: AsyncSession) -> UserRuleMatcher:
        """從 DB 載入 enabled 規則 snapshot，依 priority DESC、id ASC 排序。

        REGEX 規則於載入時預編譯並做一次性 ReDoS burn-in；burn-in 逾時的
        catastrophic pattern 會被停用（排除於 snapshot 外），確保 per-transaction
        的同步比對不致被惡意 regex 阻塞。
        """
        stmt = (
            select(UserClassificationRule, Category.category)
            .join(Category, UserClassificationRule.category_id == Category.id)
            .where(UserClassificationRule.enabled.is_(True))
            .order_by(
                UserClassificationRule.priority.desc(),
                UserClassificationRule.id.asc(),
            )
        )
        result = await session.execute(stmt)
        rules: list[UserRule] = []
        for orm_rule, category_name in result.all():
            compiled = _compile_pattern(orm_rule.pattern, orm_rule.pattern_type)
            if (
                orm_rule.pattern_type == PatternType.REGEX
                and compiled is not None
                and not await _pattern_survives_burn_in(compiled)
            ):
                logger.warning(
                    "regex rule disabled: failed ReDoS burn-in (>%dms)",
                    int(REGEX_BURN_IN_TIMEOUT_SECONDS * 1000),
                    extra={"rule_id": orm_rule.id, "pattern": orm_rule.pattern},
                )
                continue
            rules.append(
                UserRule(
                    id=orm_rule.id,
                    pattern=orm_rule.pattern,
                    pattern_type=orm_rule.pattern_type,
                    category_name=category_name,
                    priority=orm_rule.priority,
                    compiled_pattern=compiled,
                )
            )
        return cls(tuple(rules))

    @property
    def count(self) -> int:
        return len(self._rules)

    async def match(self, merchant: str) -> str | None:
        """回傳第一個命中規則的 category 名稱；無命中回 None。

        對外維持 ``async def`` 以不破壞呼叫端契約；內部比對為同步，
        KEYWORD/EXACT/REGEX 均不再 dispatch 至 executor（catastrophic regex
        已於 ``load()`` 期 burn-in 排除）。
        """
        normalized = normalize(merchant)
        for rule in self._rules:
            if self._matches(rule, normalized):
                return rule.category_name
        return None

    def _matches(self, rule: UserRule, normalized_merchant: str) -> bool:
        if rule.pattern_type == PatternType.KEYWORD:
            return normalize(rule.pattern) in normalized_merchant
        if rule.pattern_type == PatternType.EXACT:
            return normalize(rule.pattern) == normalized_merchant
        if rule.pattern_type == PatternType.REGEX:
            return self._regex_match(rule, normalized_merchant)
        return False

    def _regex_match(self, rule: UserRule, text: str) -> bool:
        """已編譯 regex 的同步 search，fail-soft（無效 regex 視為 not match）。

        優先使用 ``load()`` 時預編譯的 ``rule.compiled_pattern``；若為 ``None``
        （例如直接以建構式建立、或編譯失敗），則於此 fail-soft 編譯一次。
        經 ``load()`` 載入的規則已通過 ReDoS burn-in；直接建構的 matcher
        （測試 / 即時測試端點）不經 burn-in，但 API 層已於建立時拒收危險
        pattern（見 ``schemas.py`` 的 nested-quantifier validator）。
        """
        compiled = rule.compiled_pattern
        if compiled is None:
            compiled = _compile_pattern(rule.pattern, PatternType.REGEX)
            if compiled is None:
                # 編譯失敗已於 _compile_pattern log warning，視為 not match。
                return False
        return _re_search(compiled, text) is not None
