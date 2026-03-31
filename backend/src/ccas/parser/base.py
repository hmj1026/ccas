"""Bank parser 抽象介面。

定義所有 bank parser 必須實作的 can_parse() 與 parse() 方法。
"""

from abc import ABC, abstractmethod
from pathlib import Path

from ccas.parser.result import ParseResult


class BankParser(ABC):
    """所有 bank parser 的抽象基底類別。

    Attributes:
        bank_code: 此 parser 對應的銀行代碼（如 "CTBC"、"CATHAY"）。
        version: parser 版本號（如 "v1"、"v2"）。
    """

    bank_code: str
    version: str

    @abstractmethod
    def can_parse(self, pdf_path: Path) -> bool:
        """判斷此 parser 是否能辨識並處理指定的 PDF 檔案。

        僅負責格式辨識，不執行完整解析或資料持久化。

        Args:
            pdf_path: 已解密 PDF 的檔案路徑。

        Returns:
            True 表示此 parser 支援該格式。
        """

    @abstractmethod
    def parse(self, pdf_path: Path) -> ParseResult:
        """解析 PDF 並產出結構化帳單與交易資料。

        Args:
            pdf_path: 已解密 PDF 的檔案路徑。

        Returns:
            包含帳單摘要與交易明細的 ParseResult。

        Raises:
            ParseError: 解析過程發生不可恢復的錯誤。
        """


class ParseError(Exception):
    """Parser 解析過程中的錯誤。"""
