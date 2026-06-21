"""P3-1 層界守門：shared 不得向上依賴 pipeline；pipeline 維持 re-export 相容。

這組測試固化「stage→pipeline 解耦」的結構不變量：

1. ``ccas.shared.*`` 不得 import ``ccas.pipeline``（依賴方向僅 shared→storage）。
2. 既有 ``ccas.pipeline.{options,progress,filters}`` 的公開符號必須與
   ``ccas.shared.*`` 指向同一物件（re-export，外部呼叫端零破壞）。
3. stage 模組（ingestor/parser/decryptor/classifier/bot）不得再 import
   已解耦的 ``ccas.pipeline.{options,progress,filters}``。

匯入偵測一律走 AST（``import`` / ``from ... import``），避免 docstring 內
提及模組名造成的字串誤判。
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "ccas"

SHARED_MODULES = [
    "ccas.shared.pipeline_types",
    "ccas.shared.progress",
    "ccas.shared.filters",
]

STAGE_MODULE_FILES = [
    "ingestor/job.py",
    "parser/job.py",
    "parser/staging.py",
    "decryptor/job.py",
    "decryptor/staging.py",
    "classifier/job.py",
    "bot/job.py",
]

# P3-1 解耦範疇：progress / options / filters 三模組。``pipeline.summary``
# 的 ``NotifySummary`` 為刻意置於 pipeline 層以打破 pipeline→bot 反向相依
# （見 pipeline/summary.py docstring），屬已定案設計，不在本次解耦範疇。
DECOUPLED_PIPELINE_MODULES = {
    "ccas.pipeline.options",
    "ccas.pipeline.progress",
    "ccas.pipeline.filters",
}


def _imported_modules(source_path: Path) -> set[str]:
    """回傳檔案中所有被 import 的完整模組名（含 ``from X import`` 的 X）。"""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _module_source_path(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None, f"找不到模組 {module_name}"
    return Path(spec.origin)


@pytest.mark.parametrize("module_name", SHARED_MODULES)
def test_shared_does_not_import_pipeline(module_name: str) -> None:
    """shared 層不得向上依賴 pipeline 協調層。"""
    imported = _imported_modules(_module_source_path(module_name))
    offenders = {m for m in imported if m.startswith("ccas.pipeline")}
    assert not offenders, f"{module_name} 不得 import pipeline：{offenders}"


def test_shared_pipeline_types_exposes_pipeline_options() -> None:
    from ccas.shared.pipeline_types import PipelineOptions

    assert PipelineOptions().force is False


def test_pipeline_reexports_are_same_object() -> None:
    """pipeline 層公開符號須與 shared 指向同一物件（re-export 相容）。"""
    from ccas.pipeline import filters as pipeline_filters
    from ccas.pipeline import options as pipeline_options
    from ccas.pipeline import progress as pipeline_progress
    from ccas.shared import filters as shared_filters
    from ccas.shared import pipeline_types as shared_types
    from ccas.shared import progress as shared_progress

    assert pipeline_options.PipelineOptions is shared_types.PipelineOptions
    assert pipeline_progress.ProgressReporter is shared_progress.ProgressReporter
    assert (
        pipeline_progress.NoopProgressReporter is shared_progress.NoopProgressReporter
    )
    assert (
        pipeline_filters.apply_pipeline_filters is shared_filters.apply_pipeline_filters
    )


def test_stage_modules_do_not_import_decoupled_pipeline_modules() -> None:
    """stage 模組不得再向上 import 已解耦的 pipeline 模組。"""
    offenders: list[str] = []
    for rel in STAGE_MODULE_FILES:
        imported = _imported_modules(SRC_ROOT / rel)
        for module in imported & DECOUPLED_PIPELINE_MODULES:
            offenders.append(f"{rel} → {module}")
    assert not offenders, f"stage 模組仍向上依賴已解耦的 pipeline 模組: {offenders}"
