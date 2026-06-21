"""跨層共用的純結構/協定模組（無向上依賴 pipeline 協調層）。

依賴方向約束：``ccas.shared.*`` 僅可依賴 stdlib 與 ``ccas.storage``，
不得 import ``ccas.pipeline``。stage 模組（ingestor/parser/decryptor/
classifier/bot）改依賴本套件，以解除對 pipeline 協調層的向上相依
（P3-1）。pipeline 層保留 re-export 相容層，外部呼叫端零破壞。
"""

# 本套件刻意不在 __init__ 匯出任何符號；公開介面由各子模組（pipeline_types /
# progress / filters）各自的 __all__ 定義。明示空 __all__ 避免 star-import 誤判。
__all__: list[str] = []
