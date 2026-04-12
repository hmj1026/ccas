"""PDF 密碼解析模組。

從環境變數取得各銀行的 PDF 解密密碼。
密碼鍵值格式：PDF_PASSWORD_{BANK_CODE}（主密碼）、
PDF_PASSWORD_{BANK_CODE}_LEGACY_1..5（歷史密碼）。
"""

from ccas.config import Settings


def resolve_password(settings: Settings, bank_code: str) -> str | None:
    """取得指定銀行的 PDF 解密密碼。

    透過 ``settings.get_pdf_password()`` 從環境變數查詢。

    Args:
        settings: 應用程式設定實例。
        bank_code: 銀行代碼（不分大小寫）。

    Returns:
        密碼字串；若未設定則回傳 None。
    """
    return settings.get_pdf_password(bank_code)


def resolve_passwords(settings: Settings, bank_code: str) -> tuple[str, ...]:
    """取得指定銀行的所有候選 PDF 解密密碼。

    透過 ``settings.get_pdf_passwords()`` 從環境變數查詢，
    回傳主密碼 + legacy 密碼的順序 tuple。

    Args:
        settings: 應用程式設定實例。
        bank_code: 銀行代碼（不分大小寫）。

    Returns:
        候選密碼 tuple（主密碼優先）；若無任何密碼則為空 tuple。
    """
    return settings.get_pdf_passwords(bank_code)
