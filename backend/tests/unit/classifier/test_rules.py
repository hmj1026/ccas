"""rules 模組的單元測試。

測試 ClassificationRule 與 RuleSet 的行為。
load_rules() 需要 DB 故在 integration 測試。
"""

from ccas.classifier.rules import ClassificationRule, RuleSet


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
