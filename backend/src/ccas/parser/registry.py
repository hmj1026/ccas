"""Parser registry：依銀行代碼與版本註冊、發現、選擇 parser。

提供全域 registry 讓各 bank parser 模組自行註冊，
並根據 active_parser_version 與版本 fallback 選擇最佳 parser。
"""

from ccas.errors import ParseError
from ccas.parser.base import BankParser


class ParserNotFoundError(ParseError):
    """找不到任何可用的 parser。"""

    def __init__(self, reason: str = "", **ctx: object) -> None:
        super().__init__("找不到可用 parser", reason=reason, **ctx)


class _ParserRegistry:
    """Parser 註冊表。

    以 (bank_code, version) 為 key 儲存 parser 實例。
    """

    def __init__(self) -> None:
        self._parsers: dict[tuple[str, str], BankParser] = {}

    def register(self, parser: BankParser) -> None:
        """註冊一個 parser 實例。

        Args:
            parser: 已實例化的 BankParser，須設定 bank_code 與 version。
        """
        key = (parser.bank_code.upper(), parser.version)
        self._parsers[key] = parser

    def get_versions(self, bank_code: str) -> list[BankParser]:
        """取得某家銀行所有已註冊的 parser，依版本由新到舊排序。

        Args:
            bank_code: 銀行代碼（不分大小寫）。

        Returns:
            該銀行的 parser 列表，版本由新到舊。
            未知銀行回傳空列表。
        """
        code = bank_code.upper()
        parsers = [p for (bc, _), p in self._parsers.items() if bc == code]
        return sorted(parsers, key=lambda p: p.version, reverse=True)

    def resolve(
        self, bank_code: str, active_version: str | None = None
    ) -> list[BankParser]:
        """依首選版本與 fallback 順序取得候選 parser 列表。

        策略：
        1. 若 active_version 指定且存在，放在第一位
        2. 其餘版本依由新到舊排序（排除已放在首位的版本）

        Args:
            bank_code: 銀行代碼（不分大小寫）。
            active_version: bank_configs.active_parser_version 的值。

        Returns:
            排序後的候選 parser 列表。

        Raises:
            ParserNotFoundError: 該銀行沒有任何已註冊 parser。
        """
        code = bank_code.upper()
        all_versions = self.get_versions(code)

        if not all_versions:
            raise ParserNotFoundError(
                f"沒有已註冊的 parser：bank_code={bank_code}"
            )

        if active_version is None:
            return all_versions

        # 找到 active version 對應的 parser
        active_parser = self._parsers.get((code, active_version))

        if active_parser is None:
            # active_version 指定但不存在，回傳所有版本由新到舊
            return all_versions

        # active_version 放第一位，其餘依序排列
        rest = [p for p in all_versions if p.version != active_version]
        return [active_parser, *rest]

    def clear(self) -> None:
        """清除所有已註冊 parser（主要供測試使用）。"""
        self._parsers.clear()


# 全域 registry 單例
registry = _ParserRegistry()
