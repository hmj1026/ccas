"""Gmail API 呼叫的 exponential backoff retry。

針對暫時性錯誤（429 rate limit、5xx 伺服器錯誤）自動重試，
非暫時性錯誤直接拋出。
"""

import logging
import time
from collections.abc import Callable

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_SECONDS = (1, 2, 4)


def call_with_retry[T](fn: Callable[[], T]) -> T:
    """執行 Gmail API 呼叫，遇暫時性錯誤自動重試。

    最多重試 3 次，backoff 間隔為 1s、2s、4s。
    僅對 429（rate limit）與 5xx（伺服器錯誤）重試，
    其他 HTTP 錯誤碼直接拋出。

    Args:
        fn: 無參數 callable，呼叫 Gmail API 並回傳結果。

    Returns:
        fn() 的回傳值。

    Raises:
        HttpError: 超過重試次數或非暫時性錯誤。
    """
    last_error: HttpError | None = None

    for attempt, delay in enumerate(_BACKOFF_SECONDS):
        try:
            return fn()
        except HttpError as exc:
            if exc.resp.status not in _RETRYABLE_STATUS_CODES:
                raise
            last_error = exc
            logger.warning(
                "Gmail API 呼叫失敗 (HTTP %d)，%ds 後重試 (%d/%d)",
                exc.resp.status,
                delay,
                attempt + 1,
                len(_BACKOFF_SECONDS),
            )
            time.sleep(delay)

    # 所有重試都失敗，拋出最後一個錯誤
    raise last_error  # type: ignore[misc]
