"""使用者自訂進階分類規則 matcher（bills-management-and-insights §2）。

從 ``classification_rules`` 表載入 enabled 規則 snapshot，依 priority DESC、
id ASC 排序，逐筆比對 transaction merchant。支援三種 pattern_type：

- ``keyword``：normalize 後子字串比對（與既有 engine 同邏輯）
- ``exact``：normalize 後完全相等
- ``regex``：``re.search``，100ms timeout 保護避免 catastrophic backtracking
  阻塞 classify pipeline；timeout / 編譯錯誤皆 fail-soft（log warning + 視為
  not match），不阻斷其他規則。

設計：
- ``UserRuleMatcher.load(session)`` 一次性 query 規則 + 對應 category 名，
  避免 N+1 查詢；之後對每筆 transaction 走 in-memory snapshot
- regex 透過 ``asyncio.wait_for(loop.run_in_executor(...), timeout=0.1)``
  實現 timeout；executor thread 雖無法真的中斷 ``re.search``，但不會阻塞
  caller 的事件迴圈
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

REGEX_TIMEOUT_SECONDS: float = 0.1


def _re_search(pattern: str, text: str) -> re.Match[str] | None:
    """re.search 的薄包裝，作為測試 monkeypatch 的注入點。"""
    return re.search(pattern, text)


@dataclass(frozen=True)
class UserRule:
    """In-memory snapshot of a single user classification rule.

    與 ``UserClassificationRule`` ORM model 解耦，避免 detached instance 問題。
    ``category_name`` 為 JOIN ``categories.category`` 後的字串值。
    """

    id: int
    pattern: str
    pattern_type: PatternType
    category_name: str
    priority: int


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
        """從 DB 載入 enabled 規則 snapshot，依 priority DESC、id ASC 排序。"""
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
        rules = tuple(
            UserRule(
                id=row[0].id,
                pattern=row[0].pattern,
                pattern_type=row[0].pattern_type,
                category_name=row[1],
                priority=row[0].priority,
            )
            for row in result.all()
        )
        return cls(rules)

    @property
    def count(self) -> int:
        return len(self._rules)

    async def match(self, merchant: str) -> str | None:
        """回傳第一個命中規則的 category 名稱；無命中回 None。"""
        normalized = normalize(merchant)
        for rule in self._rules:
            if await self._matches(rule, normalized):
                return rule.category_name
        return None

    async def _matches(self, rule: UserRule, normalized_merchant: str) -> bool:
        if rule.pattern_type == PatternType.KEYWORD:
            return normalize(rule.pattern) in normalized_merchant
        if rule.pattern_type == PatternType.EXACT:
            return normalize(rule.pattern) == normalized_merchant
        if rule.pattern_type == PatternType.REGEX:
            return await self._regex_match(rule.pattern, normalized_merchant)
        return False

    async def _regex_match(self, pattern: str, text: str) -> bool:
        """re.search 含 100ms timeout 與 fail-soft 行為。"""
        loop = asyncio.get_running_loop()
        try:
            match = await asyncio.wait_for(
                loop.run_in_executor(None, _re_search, pattern, text),
                timeout=REGEX_TIMEOUT_SECONDS,
            )
            return match is not None
        except TimeoutError:
            logger.warning(
                "regex pattern exceeded %dms timeout, treating as no match",
                int(REGEX_TIMEOUT_SECONDS * 1000),
                extra={"pattern": pattern},
            )
            return False
        except re.error as exc:
            logger.warning(
                "regex pattern error, treating as no match",
                extra={"pattern": pattern, "error": str(exc)},
            )
            return False
