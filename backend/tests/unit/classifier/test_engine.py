"""classification engine 的單元測試。

測試正規化、最長關鍵字匹配、tie-break、未分類情境。
"""

import pytest

from ccas.classifier.engine import DEFAULT_CATEGORY, classify, normalize
from ccas.classifier.rules import ClassificationRule, RuleSet


class TestNormalize:
    def test_strip_whitespace(self) -> None:
        assert normalize("  星巴克  ") == "星巴克"

    def test_collapse_multiple_spaces(self) -> None:
        assert normalize("星  巴  克") == "星 巴 克"

    def test_lowercase_ascii(self) -> None:
        assert normalize("STARBUCKS") == "starbucks"

    def test_mixed_case_with_spaces(self) -> None:
        assert normalize("  Star  BUCKS  ") == "star bucks"

    def test_empty_string(self) -> None:
        assert normalize("") == ""

    def test_tabs_and_newlines(self) -> None:
        assert normalize("star\tbucks\ncoffee") == "star bucks coffee"


class TestClassify:
    def _make_rule(
        self, rule_id: int, keyword: str, category: str
    ) -> ClassificationRule:
        return ClassificationRule(
            rule_id=rule_id, keyword=keyword, category=category
        )

    def test_single_match(self) -> None:
        rules = RuleSet(rules=(
            self._make_rule(1, "星巴克", "餐飲"),
        ))
        assert classify("星巴克咖啡 信義店", rules) == "餐飲"

    def test_no_match_returns_default(self) -> None:
        rules = RuleSet(rules=(
            self._make_rule(1, "星巴克", "餐飲"),
        ))
        assert classify("全聯福利中心", rules) == DEFAULT_CATEGORY

    def test_empty_rules_returns_default(self) -> None:
        rules = RuleSet(rules=())
        assert classify("任何商家", rules) == DEFAULT_CATEGORY

    def test_longest_keyword_wins(self) -> None:
        """同一商家命中多個關鍵字時，取最長者。"""
        rules = RuleSet(rules=(
            self._make_rule(1, "台灣", "其他"),
            self._make_rule(2, "台灣大哥大", "通訊"),
        ))
        assert classify("台灣大哥大月租費", rules) == "通訊"

    def test_same_length_smaller_id_wins(self) -> None:
        """同長度關鍵字 tie-break：較小 id 優先。"""
        rules = RuleSet(rules=(
            self._make_rule(5, "咖啡", "餐飲"),
            self._make_rule(2, "咖啡", "飲料"),
        ))
        assert classify("咖啡廳消費", rules) == "飲料"

    def test_case_insensitive_match(self) -> None:
        rules = RuleSet(rules=(
            self._make_rule(1, "starbucks", "餐飲"),
        ))
        assert classify("STARBUCKS COFFEE", rules) == "餐飲"

    def test_keyword_case_insensitive(self) -> None:
        """關鍵字本身大小寫也做正規化。"""
        rules = RuleSet(rules=(
            self._make_rule(1, "AMAZON", "購物"),
        ))
        assert classify("amazon prime", rules) == "購物"

    def test_whitespace_normalization_in_merchant(self) -> None:
        rules = RuleSet(rules=(
            self._make_rule(1, "全聯", "超市"),
        ))
        assert classify("  全聯  福利中心  ", rules) == "超市"

    def test_multiple_matches_longest_wins(self) -> None:
        """三個規則同時命中，最長的贏。"""
        rules = RuleSet(rules=(
            self._make_rule(1, "7", "便利商店"),
            self._make_rule(2, "7-11", "便利商店"),
            self._make_rule(3, "7-eleven", "超商"),
        ))
        assert classify("7-ELEVEN 忠孝店", rules) == "超商"

    def test_default_category_value(self) -> None:
        assert DEFAULT_CATEGORY == "未分類"

    @pytest.mark.parametrize(
        "merchant",
        ["", "   ", "\t\n"],
    )
    def test_blank_merchant_returns_default(self, merchant: str) -> None:
        rules = RuleSet(rules=(
            self._make_rule(1, "星巴克", "餐飲"),
        ))
        assert classify(merchant, rules) == DEFAULT_CATEGORY
