"""FetcherRegistry -- 銀行 web-fetcher 註冊與查找。

提供全域 registry 讓各 bank fetcher 模組自行註冊，
並依 bank_code 查找對應的 fetcher 實例。
"""

from __future__ import annotations

import logging

from ccas.ingestor.fetcher.base import BankFetcher

logger = logging.getLogger(__name__)


class _FetcherRegistry:
    """Fetcher 註冊表。

    以 bank_code 為 key 儲存 fetcher 實例。
    """

    def __init__(self) -> None:
        self._fetchers: dict[str, BankFetcher] = {}

    def register(self, fetcher: BankFetcher) -> None:
        """註冊一個 fetcher 實例。

        Args:
            fetcher: 已實例化的 BankFetcher。
        """
        code = fetcher.bank_code.upper()
        self._fetchers[code] = fetcher
        logger.debug("已註冊 fetcher: %s", code)

    def get(self, bank_code: str) -> BankFetcher | None:
        """依銀行代碼查找 fetcher。

        Args:
            bank_code: 銀行代碼（不分大小寫）。

        Returns:
            對應的 BankFetcher 實例，若未註冊則回傳 None。
        """
        return self._fetchers.get(bank_code.upper())

    def clear(self) -> None:
        """清除所有已註冊 fetcher（主要供測試使用）。"""
        self._fetchers.clear()


# 全域 registry 單例
fetcher_registry = _FetcherRegistry()
