"""BankFetcher 框架：銀行帳單 web-fetch 抽象介面與註冊機制。"""

from ccas.ingestor.fetcher import banks as _banks  # noqa: F401 -- trigger registration
from ccas.ingestor.fetcher.registry import fetcher_registry

__all__ = ["fetcher_registry"]
