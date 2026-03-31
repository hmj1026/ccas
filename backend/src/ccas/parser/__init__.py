"""PDF 解析模組。

提供 bank parser 介面、registry、batch parse job，
將解密後的 PDF 轉為結構化帳單與交易資料。
"""

from ccas.parser.base import BankParser, ParseError
from ccas.parser.job import ParseSummary, run_parse_job
from ccas.parser.registry import ParserNotFoundError, registry
from ccas.parser.result import ParseResult, TransactionItem

__all__ = [
    "BankParser",
    "ParseError",
    "ParseResult",
    "ParseSummary",
    "ParserNotFoundError",
    "TransactionItem",
    "registry",
    "run_parse_job",
]
