"""Shared query filters for pipeline stages（相容 re-export）。

P3-1 起 ``apply_pipeline_filters`` 定義移至 ``ccas.shared.filters``（依賴方向
shared→storage）以解除 stage→pipeline 的向上相依。本模組保留為相容層，
既有 ``from ccas.pipeline.filters import apply_pipeline_filters`` 呼叫端零破壞。
"""

from ccas.shared.filters import apply_pipeline_filters

__all__ = ["apply_pipeline_filters"]
