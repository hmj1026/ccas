"""CcasError 例外階層的單元測試。"""

import pytest

from ccas.errors import (
    CcasError,
    ClassifyError,
    DecryptError,
    IngestError,
    NotifyError,
    ParseError,
)


class TestCcasErrorBase:
    """CcasError 基底類別測試。"""

    def test_inherits_exception(self) -> None:
        assert issubclass(CcasError, Exception)

    def test_default_fields(self) -> None:
        err = CcasError()
        assert err.message == ""
        assert err.context == {}

    def test_message_stored(self) -> None:
        err = CcasError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_context_preserved(self) -> None:
        ctx = {"file": "test.pdf", "bank": "CTBC"}
        err = CcasError("fail", context=ctx)
        assert err.context == ctx

    def test_context_defaults_to_empty_dict(self) -> None:
        err = CcasError("fail")
        assert err.context == {}
        assert isinstance(err.context, dict)


class TestSubclassInheritance:
    """所有子類別均繼承 CcasError。"""

    @pytest.mark.parametrize(
        "cls",
        [IngestError, DecryptError, ParseError, ClassifyError, NotifyError],
    )
    def test_is_subclass_of_ccas_error(self, cls: type) -> None:
        assert issubclass(cls, CcasError)

    @pytest.mark.parametrize(
        "cls",
        [IngestError, DecryptError, ParseError, ClassifyError, NotifyError],
    )
    def test_catchable_as_ccas_error(self, cls: type) -> None:
        with pytest.raises(CcasError):
            raise cls("desc", reason="reason")

    @pytest.mark.parametrize(
        "cls",
        [IngestError, DecryptError, ParseError, ClassifyError, NotifyError],
    )
    def test_catchable_as_own_type(self, cls: type) -> None:
        with pytest.raises(cls):
            raise cls("desc", reason="reason")


class TestMessageFormat:
    """錯誤訊息格式：[ModuleName] <描述>: <原因>。"""

    @pytest.mark.parametrize(
        ("cls", "module_name"),
        [
            (IngestError, "Ingest"),
            (DecryptError, "Decrypt"),
            (ParseError, "Parse"),
            (ClassifyError, "Classify"),
            (NotifyError, "Notify"),
        ],
    )
    def test_format_with_reason(self, cls: type, module_name: str) -> None:
        err = cls("操作失敗", reason="檔案不存在")
        expected = f"[{module_name}] 操作失敗: 檔案不存在"
        assert err.message == expected
        assert str(err) == expected

    @pytest.mark.parametrize(
        ("cls", "module_name"),
        [
            (IngestError, "Ingest"),
            (DecryptError, "Decrypt"),
            (ParseError, "Parse"),
            (ClassifyError, "Classify"),
            (NotifyError, "Notify"),
        ],
    )
    def test_format_without_reason(self, cls: type, module_name: str) -> None:
        err = cls("操作失敗")
        expected = f"[{module_name}] 操作失敗"
        assert err.message == expected

    def test_context_passed_via_kwargs(self) -> None:
        err = DecryptError("解密失敗", reason="密碼錯誤", file="a.pdf", bank="CTBC")
        assert err.context == {"file": "a.pdf", "bank": "CTBC"}
