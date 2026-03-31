"""Telegram API 呼叫封裝。

提供 sendMessage 的 exponential backoff retry 機制，
針對 429（rate limit）與 5xx（暫時性錯誤）自動重試。
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


async def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """透過 Telegram Bot API 發送訊息，含 exponential backoff retry。

    針對 429 與 5xx 狀態碼自動重試（最多 3 次，間隔 1s/2s/4s）。
    非暫時性錯誤（如 4xx）不重試，直接拋出。

    Args:
        bot_token: Telegram Bot API 權杖。
        chat_id: 目標聊天室 ID。
        text: 訊息內容。
        max_retries: 最大重試次數。
        base_delay: 基礎延遲秒數。
        http_client: 可選的 httpx 非同步客戶端（測試注入用）。

    Returns:
        Telegram API 回應 JSON。

    Raises:
        httpx.HTTPStatusError: 非暫時性錯誤或重試次數用盡。
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    async def _do_send(client: httpx.AsyncClient) -> dict:
        last_error: httpx.HTTPStatusError | None = None

        for attempt in range(max_retries + 1):
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                return response.json()

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                response.raise_for_status()

            last_error = httpx.HTTPStatusError(
                message=f"Telegram API error: {response.status_code}",
                request=response.request,
                response=response,
            )

            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Telegram API %d, retry %d/%d after %.1fs",
                    response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)

        logger.error(
            "Telegram API failed after %d retries", max_retries
        )
        raise last_error  # type: ignore[misc]

    if http_client is not None:
        return await _do_send(http_client)

    async with httpx.AsyncClient() as client:
        return await _do_send(client)
