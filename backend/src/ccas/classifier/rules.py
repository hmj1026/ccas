"""分類規則載入與記憶體表示。

從 categories 資料表載入關鍵字-分類映射，
提供 RuleSet 作為分類引擎查詢的唯一來源。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Category


@dataclass(frozen=True)
class ClassificationRule:
    """單一分類規則（不可變）。

    Attributes:
        rule_id: categories 表的主鍵。
        keyword: 比對用關鍵字（原始值，尚未正規化）。
        category: 對應的分類名稱。
    """

    rule_id: int
    keyword: str
    category: str


@dataclass(frozen=True)
class RuleSet:
    """規則集合（不可變）。

    載入後即為 snapshot，不會自動反映資料表的後續變更。
    需要更新時呼叫 load_rules() 取得新的 RuleSet。
    """

    rules: tuple[ClassificationRule, ...]

    @property
    def count(self) -> int:
        return len(self.rules)


async def load_rules(session: AsyncSession) -> RuleSet:
    """從 categories 資料表載入所有分類規則。

    Args:
        session: 非同步 DB Session。

    Returns:
        包含所有規則的 RuleSet 快照。
    """
    stmt = select(Category).order_by(Category.id)
    result = await session.execute(stmt)
    rows: Sequence[Category] = result.scalars().all()

    rules = tuple(
        ClassificationRule(
            rule_id=row.id,
            keyword=row.keyword,
            category=row.category,
        )
        for row in rows
    )
    return RuleSet(rules=rules)
