"""PDF 解密核心模組。

使用 pikepdf 嘗試開啟 PDF 檔案，偵測是否加密，
並以指定密碼解密後覆寫原始檔案（in-place）。
"""

from dataclasses import dataclass
from pathlib import Path

import pikepdf


class DecryptionError(Exception):
    """PDF 解密失敗時拋出的例外。"""


@dataclass(frozen=True)
class DecryptResult:
    """PDF 解密結果。

    Attributes:
        needed_decryption: True 表示 PDF 原本加密且已成功解密；
                           False 表示 PDF 未加密，直接透通。
    """

    needed_decryption: bool


def decrypt_pdf(pdf_path: Path, password: str | None) -> DecryptResult:
    """嘗試解密 PDF 檔案並覆寫原始路徑。

    流程：
    1. 嘗試無密碼開啟 -- 成功表示未加密，直接透通
    2. 若拋出 PasswordError 且無密碼可用 -- 拋出 DecryptionError
    3. 以密碼開啟 -- 成功則覆寫原始檔案；仍失敗則拋出 DecryptionError

    Args:
        pdf_path: PDF 檔案路徑。
        password: 解密密碼；若為 None 且 PDF 加密則會失敗。

    Returns:
        DecryptResult 描述解密結果。

    Raises:
        DecryptionError: 密碼缺漏或錯誤導致無法解密。
        FileNotFoundError: PDF 檔案不存在。
    """
    try:
        with pikepdf.open(pdf_path) as pdf:
            pdf.save(pdf_path)
            return DecryptResult(needed_decryption=False)
    except pikepdf.PasswordError:
        pass

    if password is None:
        raise DecryptionError("Password not found in settings")

    try:
        with pikepdf.open(pdf_path, password=password) as pdf:
            pdf.save(pdf_path)
            return DecryptResult(needed_decryption=True)
    except pikepdf.PasswordError:
        raise DecryptionError("Invalid password")
