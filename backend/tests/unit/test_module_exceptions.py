"""模組專屬例外的訊息格式驗證。

驗證各模組在拋出模組專屬例外時，錯誤訊息格式符合
[ModuleName] <描述>: <原因> 規範。
"""

import re

import pytest

from ccas.decryptor.decrypt import DecryptionError
from ccas.errors import CcasError
from ccas.ingestor.auth import GmailAuthError
from ccas.parser.registry import ParserNotFoundError

# 預期格式：[ModuleName] 描述: 原因
_FORMAT_RE = re.compile(r"^\[\w+\] .+: .+$")


class TestDecryptionErrorFormat:
    """DecryptionError 繼承 DecryptError 並符合訊息格式。"""

    def test_inherits_ccas_error(self) -> None:
        assert issubclass(DecryptionError, CcasError)

    def test_message_format(self) -> None:
        err = DecryptionError("Invalid password")
        assert _FORMAT_RE.match(err.message), f"格式不符：{err.message}"
        assert "[Decrypt]" in err.message

    def test_catchable_as_ccas_error(self) -> None:
        with pytest.raises(CcasError):
            raise DecryptionError("bad password")


class TestGmailAuthErrorFormat:
    """GmailAuthError 繼承 IngestError 並符合訊息格式。"""

    def test_inherits_ccas_error(self) -> None:
        assert issubclass(GmailAuthError, CcasError)

    def test_message_format(self) -> None:
        err = GmailAuthError("token expired")
        assert _FORMAT_RE.match(err.message), f"格式不符：{err.message}"
        assert "[Ingest]" in err.message

    def test_catchable_as_ccas_error(self) -> None:
        with pytest.raises(CcasError):
            raise GmailAuthError("no token")


class TestParserNotFoundErrorFormat:
    """ParserNotFoundError 繼承 ParseError 並符合訊息格式。"""

    def test_inherits_ccas_error(self) -> None:
        assert issubclass(ParserNotFoundError, CcasError)

    def test_message_format(self) -> None:
        err = ParserNotFoundError("bank_code=XYZ")
        assert _FORMAT_RE.match(err.message), f"格式不符：{err.message}"
        assert "[Parse]" in err.message

    def test_catchable_as_ccas_error(self) -> None:
        with pytest.raises(CcasError):
            raise ParserNotFoundError("no parser")
