"""關鍵字分類引擎。

根據正規化後的商家名稱與 RuleSet 中的關鍵字進行比對，
採用最長關鍵字優先、同長度以較小 id 決定的 deterministic 規則。
無命中時回傳固定分類值 ``未分類``。
"""

import re

from ccas.classifier.rules import ClassificationRule, RuleSet
from ccas.constants import DEFAULT_CATEGORY  # re-export for backward compat


def normalize(text: str) -> str:
    """正規化商家名稱。

    處理：
    1. 去除前後空白
    2. 壓縮連續空白為單一空格
    3. 轉為 ASCII 小寫（case-insensitive 比對）

    Args:
        text: 原始商家名稱。

    Returns:
        正規化後的字串。
    """
    stripped = text.strip()
    collapsed = re.sub(r"\s+", " ", stripped)
    return collapsed.lower()


def classify(merchant: str, rule_set: RuleSet) -> str:
    """根據 RuleSet 為商家名稱進行分類。

    比對規則：
    - 關鍵字與商家名稱皆先正規化再做子字串比對
    - 多個關鍵字命中時，取最長關鍵字
    - 長度相同時，取 rule_id 較小者
    - 無命中回傳 ``未分類``

    Args:
        merchant: 原始商家名稱。
        rule_set: 分類規則集合。

    Returns:
        匹配的分類名稱，或 ``未分類``。
    """
    normalized_merchant = normalize(merchant)

    best: ClassificationRule | None = None

    for rule in rule_set.rules:
        normalized_keyword = normalize(rule.keyword)
        if normalized_keyword not in normalized_merchant:
            continue
        if best is None:
            best = rule
            continue
        # 最長關鍵字優先；同長度取較小 id
        best_len = len(normalize(best.keyword))
        curr_len = len(normalized_keyword)
        if curr_len > best_len:
            best = rule
        elif curr_len == best_len and rule.rule_id < best.rule_id:
            best = rule

    if best is None:
        return DEFAULT_CATEGORY
    return best.category
