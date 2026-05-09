"""Registry 與 parser 選擇順序的單元測試。"""

from pathlib import Path

import pytest

from ccas.parser.base import BankParser
from ccas.parser.registry import ParserNotFoundError, _ParserRegistry
from ccas.parser.result import ParseResult


class FakeParser(BankParser):
    """測試用的假 parser。"""

    def __init__(self, bank_code: str, version: str) -> None:
        self.bank_code = bank_code
        self.version = version

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        raise NotImplementedError


class TestParserRegistry:
    """_ParserRegistry 的單元測試。"""

    def setup_method(self) -> None:
        self.reg = _ParserRegistry()

    def test_register_and_get_versions(self) -> None:
        """註冊多個版本後可取回，且依版本由新到舊排序。"""
        p1 = FakeParser("CTBC", "v1")
        p2 = FakeParser("CTBC", "v2")
        self.reg.register(p1)
        self.reg.register(p2)

        versions = self.reg.get_versions("CTBC")
        assert len(versions) == 2
        assert versions[0].version == "v2"
        assert versions[1].version == "v1"

    def test_get_versions_case_insensitive(self) -> None:
        """bank_code 不分大小寫。"""
        self.reg.register(FakeParser("ctbc", "v1"))
        assert len(self.reg.get_versions("CTBC")) == 1
        assert len(self.reg.get_versions("ctbc")) == 1

    def test_get_versions_unknown_bank_returns_empty(self) -> None:
        """未知銀行回傳空列表。"""
        assert self.reg.get_versions("UNKNOWN") == []

    def test_resolve_with_active_version_first(self) -> None:
        """active_version 存在時放在第一位。"""
        self.reg.register(FakeParser("CTBC", "v1"))
        self.reg.register(FakeParser("CTBC", "v2"))
        self.reg.register(FakeParser("CTBC", "v3"))

        candidates = self.reg.resolve("CTBC", active_version="v2")
        assert candidates[0].version == "v2"
        assert candidates[1].version == "v3"
        assert candidates[2].version == "v1"

    def test_resolve_active_version_not_registered(self) -> None:
        """active_version 指定但不存在時，回傳所有版本由新到舊。"""
        self.reg.register(FakeParser("CTBC", "v1"))
        self.reg.register(FakeParser("CTBC", "v2"))

        candidates = self.reg.resolve("CTBC", active_version="v99")
        assert candidates[0].version == "v2"
        assert candidates[1].version == "v1"

    def test_resolve_no_active_version(self) -> None:
        """未指定 active_version 時回傳由新到舊。"""
        self.reg.register(FakeParser("CATHAY", "v1"))
        self.reg.register(FakeParser("CATHAY", "v3"))

        candidates = self.reg.resolve("CATHAY", active_version=None)
        assert candidates[0].version == "v3"
        assert candidates[1].version == "v1"

    def test_resolve_unknown_bank_raises(self) -> None:
        """未知銀行 raise ParserNotFoundError。"""
        with pytest.raises(ParserNotFoundError, match="UNKNOWN"):
            self.reg.resolve("UNKNOWN")

    def test_resolve_different_banks_isolated(self) -> None:
        """不同銀行的 parser 互不影響。"""
        self.reg.register(FakeParser("CTBC", "v1"))
        self.reg.register(FakeParser("CATHAY", "v1"))

        ctbc = self.reg.resolve("CTBC")
        assert len(ctbc) == 1
        assert ctbc[0].bank_code.upper() == "CTBC"

    def test_clear_removes_all(self) -> None:
        """clear() 清除所有已註冊 parser。"""
        self.reg.register(FakeParser("CTBC", "v1"))
        self.reg.clear()
        assert self.reg.get_versions("CTBC") == []
