"""Telegram Bot 認證模組。

提供 chat_id 白名單驗證，從 Settings 提供的原始字串解析。
"""


def load_allowed_chat_ids(raw: str) -> frozenset[int]:
    """解析逗號分隔的 chat_id 字串為 frozenset。

    Args:
        raw: 逗號分隔的 chat_id 字串，例如 ``"123,456,789"``。

    Returns:
        不可變的 chat_id 集合。空字串回傳空 frozenset。
    """
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
