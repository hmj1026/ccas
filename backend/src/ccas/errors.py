"""CCAS 共用例外定義。"""


class CcasError(Exception):
    """CCAS 所有可恢復錯誤的基底例外。

    用於 pipeline 執行異常，供 RQ job 重試邏輯捕捉。
    """
