"""Pipeline execution options（相容 re-export）。

P3-1 起 ``PipelineOptions`` 定義移至 ``ccas.shared.pipeline_types`` 以解除
stage→pipeline 的向上相依。本模組保留為相容層，既有
``from ccas.pipeline.options import PipelineOptions`` 呼叫端零破壞。
"""

from ccas.shared.pipeline_types import PipelineOptions

__all__ = ["PipelineOptions"]
