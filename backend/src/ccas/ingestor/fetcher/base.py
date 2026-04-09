"""BankFetcher 抽象基底類別與相關例外。"""

from __future__ import annotations

import abc


class FetchError(Exception):
    """Web-fetch 操作失敗。

    Attributes:
        bank_code: 發生錯誤的銀行代碼。
    """

    def __init__(self, bank_code: str, message: str) -> None:
        self.bank_code = bank_code
        super().__init__(f"[{bank_code}] {message}")


class BankFetcher(abc.ABC):
    """銀行帳單 web-fetch 抽象介面。

    子類別須實作 bank_code property、can_fetch() 與 fetch_pdf() 方法。
    """

    @property
    @abc.abstractmethod
    def bank_code(self) -> str:
        """此 fetcher 對應的銀行代碼。"""
        ...

    @abc.abstractmethod
    def can_fetch(self, html_body: str) -> bool:
        """判斷 HTML 郵件內容是否包含可下載的帳單連結。

        Args:
            html_body: 郵件的 HTML 內容。

        Returns:
            True 表示此 fetcher 能處理該郵件。
        """
        ...

    @abc.abstractmethod
    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        """從 HTML 郵件中的連結下載 PDF 帳單。

        Args:
            html_body: 郵件的 HTML 內容。
            credentials: 銀行驗證所需的憑證字典。

        Returns:
            下載的 PDF 檔案原始位元組。

        Raises:
            FetchError: 下載過程中發生錯誤。
        """
        ...
