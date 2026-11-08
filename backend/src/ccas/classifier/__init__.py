"""消費類別分類。

對外介面是 :class:`Classifier`（分類判定）；``engine`` / ``rules`` /
``user_rules`` 是它的內部組成。
"""

from ccas.classifier.decision import CategoryDecision, Classifier, DecisionSource

__all__ = ["CategoryDecision", "Classifier", "DecisionSource"]
