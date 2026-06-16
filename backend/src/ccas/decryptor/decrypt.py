"""PDF 解密核心模組。

使用 pikepdf 嘗試開啟 PDF 檔案，偵測是否加密，並以指定密碼解密後
*原子性* 覆寫原始檔案：來源以唯讀開啟，解密結果先寫入同目錄的暫存檔，
成功後才以 ``os.replace`` 換入。中途崩潰只會留下暫存檔，原始 PDF 不會
半寫損毀。
"""

from dataclasses import dataclass
from pathlib import Path

import pikepdf

from ccas.errors import DecryptError
from ccas.storage.atomic import atomic_replace_via


class DecryptionError(DecryptError):
    """PDF 解密失敗時拋出的例外。"""

    def __init__(self, reason: str = "", **ctx: object) -> None:
        super().__init__("PDF 解密失敗", reason=reason, **ctx)


def _save_decrypted(pdf_path: Path, password: str | None) -> None:
    """Open *pdf_path* read-only and atomically overwrite it decrypted.

    The source is opened without ``allow_overwriting_input`` so pikepdf keeps a
    read-only handle; the decrypted output is written to a same-directory temp
    file and ``os.replace``-d into place. ``pikepdf.PasswordError`` propagates to
    let the caller try the next candidate password; any ``OSError`` from save or
    rename also propagates so the job marks the attachment failed (never
    swallowed). Leftover temp files are removed by ``atomic_replace_via``.
    """
    # pikepdf.open expects str | bytes for password; an empty string means
    # "no password" and is equivalent to the prior no-arg open() call.
    with pikepdf.open(pdf_path, password=password or "") as pdf:
        atomic_replace_via(pdf_path, pdf.save, suffix=".dec.tmp")


@dataclass(frozen=True)
class DecryptResult:
    """PDF 解密結果。

    Attributes:
        needed_decryption: True 表示 PDF 原本加密且已成功解密；
                           False 表示 PDF 未加密，直接透通。
    """

    needed_decryption: bool


def decrypt_pdf_multi(pdf_path: Path, passwords: tuple[str, ...]) -> DecryptResult:
    """嘗試以多組候選密碼解密 PDF 檔案。

    流程：
    1. 嘗試無密碼開啟 -- 成功表示未加密，直接透通
    2. 依序嘗試 passwords tuple 中每個密碼
    3. 任一成功即覆寫原始檔案並回傳
    4. 全失敗或無候選密碼則拋出 DecryptionError

    Args:
        pdf_path: PDF 檔案路徑。
        passwords: 候選密碼 tuple（主密碼優先）。

    Returns:
        DecryptResult 描述解密結果。

    Raises:
        DecryptionError: 密碼缺漏或全部錯誤導致無法解密。
        FileNotFoundError: PDF 檔案不存在。
    """
    try:
        _save_decrypted(pdf_path, password=None)
        return DecryptResult(needed_decryption=False)
    except pikepdf.PasswordError:
        pass

    if not passwords:
        raise DecryptionError("Password not found in settings")

    for pw in passwords:
        try:
            _save_decrypted(pdf_path, password=pw)
            return DecryptResult(needed_decryption=True)
        except pikepdf.PasswordError:
            continue

    raise DecryptionError(f"Invalid password (tried {len(passwords)} candidates)")


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
        _save_decrypted(pdf_path, password=None)
        return DecryptResult(needed_decryption=False)
    except pikepdf.PasswordError:
        pass

    if password is None:
        raise DecryptionError("Password not found in settings")

    try:
        _save_decrypted(pdf_path, password=password)
        return DecryptResult(needed_decryption=True)
    except pikepdf.PasswordError as exc:
        raise DecryptionError("Invalid password") from exc
