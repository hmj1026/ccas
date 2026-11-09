"""分類判定（Category decision）。

決定一筆交易消費類別的唯一位置。pipeline classify 階段、全量重新分類與清除
手動分類覆寫的端點都透過 :class:`Classifier` 取得判定，確保三者結果一致。

判定順序：手動分類覆寫（保留既有消費類別）→ 分類規則（priority 高者先、相同
priority 依 id）→ 內建關鍵字規則 → 預設消費類別。比對一律使用交易的原始商家
名稱；商家別名只是顯示名稱，不影響分類。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ccas.classifier.engine import classify
from ccas.classifier.rules import RuleSet, load_rules
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.constants import DEFAULT_CATEGORY

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ccas.storage.models import Transaction


class DecisionSource(StrEnum):
    MANUAL_OVERRIDE = "manual_override"
    USER_RULE = "user_rule"
    KEYWORD = "keyword"
    DEFAULT = "default"


@dataclass(frozen=True)
class CategoryDecision:
    """分類判定結果。``category`` 只有在手動分類覆寫時為 ``None``（保留既有值）。"""

    category: str | None
    source: DecisionSource


class Classifier:
    """以一份規則快照決定交易的消費類別。

    建構時接受已載入的分類規則與關鍵字規則（測試可不經 DB 建立）；正式路徑用
    :meth:`load` 一次載入。``decide`` 沒有副作用：不寫交易、不碰 session。
    """

    def __init__(self, user_rules: UserRuleMatcher, keyword_rules: RuleSet) -> None:
        self._user_rules = user_rules
        self._keyword_rules = keyword_rules

    @classmethod
    async def load(cls, session: AsyncSession) -> Classifier:
        """載入目前啟用的分類規則（含 ReDoS burn-in）與關鍵字規則。"""
        return cls(await UserRuleMatcher.load(session), await load_rules(session))

    async def decide(self, txn: Transaction) -> CategoryDecision:
        if txn.manual_category_override:
            return CategoryDecision(None, DecisionSource.MANUAL_OVERRIDE)
        user_category = await self._user_rules.match(txn.merchant)
        if user_category is not None:
            return CategoryDecision(user_category, DecisionSource.USER_RULE)
        category = classify(txn.merchant, self._keyword_rules)
        if category == DEFAULT_CATEGORY:
            return CategoryDecision(category, DecisionSource.DEFAULT)
        return CategoryDecision(category, DecisionSource.KEYWORD)
