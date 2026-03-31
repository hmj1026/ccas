"""Telegram Bot 認證模組。

提供 chat_id 白名單驗證，從環境變數 TELEGRAM_ALLOWED_CHAT_IDS 讀取。
"""

import os


def load_allowed_chat_ids() -> frozenset[int]:
    """從環境變數載入允許的 chat_id 清單。

    環境變數 ``TELEGRAM_ALLOWED_CHAT_IDS`` 以逗號分隔，例如 ``123,456,789``。
    若未設定或為空字串，回傳空 frozenset。

    Returns:
        不可變的 chat_id 集合。
    """
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    if not raw.strip():
        return frozenset()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return frozenset(int(p) for p in parts)


def is_chat_allowed(chat_id: int, allowed: frozenset[int]) -> bool:
    """檢查 chat_id 是否在白名單中。

    Args:
        chat_id: 來源聊天室 ID。
        allowed: 白名單 chat_id 集合。

    Returns:
        True 表示允許，False 表示應靜默忽略。
    """
    return chat_id in allowed
