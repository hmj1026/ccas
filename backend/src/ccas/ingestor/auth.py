"""Gmail OAuth 憑證載入與 token 自動刷新。

負責從本地 token 檔案載入已授權的 OAuth 憑證，
並在 access token 過期時自動刷新。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ccas.errors import IngestError
from ccas.storage.oauth_secrets import (
    read_token_payload,
    write_encrypted_token_file,
)

if TYPE_CHECKING:
    from ccas.storage.secrets import MasterKeyManager

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


def write_private_token_file(path: Path, content: str) -> None:
    """以 0600 權限原子建檔寫入 token，避免 write→chmod 之間的 race window。

    對照 ``storage.secrets.MasterKeyManager``：直接用 ``os.open`` 帶
    ``0o600`` mode 建檔，讓檔案從一開始就是 owner-only，而非先以預設
    umask 落地再 chmod（後者有短暫世界可讀的時間窗,可能洩漏 OAuth token）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    except (OSError, UnicodeEncodeError):
        # fdopen / write 失敗時 fd 可能尚未被接管，需手動關閉避免洩漏。
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    # 防禦性 chmod：對抗少數系統下 umask 仍影響 os.open mode 的情況。
    os.chmod(path, 0o600)


class GmailAuthError(IngestError):
    """Gmail OAuth 驗證失敗。"""

    def __init__(self, reason: str = "", **ctx: object) -> None:
        super().__init__("Gmail OAuth 驗證失敗", reason=reason, **ctx)


def _resolve_master_key_manager(
    manager: MasterKeyManager | None,
) -> MasterKeyManager:
    """Return *manager* if given, else the process Settings' manager."""
    if manager is not None:
        return manager
    from ccas.config import get_settings

    return get_settings().master_key_manager


def load_credentials(
    credentials_path: str,
    token_path: str,
    manager: MasterKeyManager | None = None,
) -> Credentials:
    """從 token.json 載入 OAuth Credentials，必要時自動刷新。

    token.json 以 master.key Fernet 加密落檔（envelope 格式）；本函式讀取時
    解密，並向後相容既有 plaintext token.json。刷新成功後回寫 **加密** token，
    確保下一次刷新不會把 refresh_token 重新明文化（spec Stage 6 A3）。

    Args:
        credentials_path: OAuth 應用程式憑證 JSON 檔路徑（首次授權時使用）。
        token_path: 授權後保存的 token JSON 檔路徑。
        manager: ``MasterKeyManager``；省略時由 ``get_settings`` 取得（注入便於測試）。

    Returns:
        有效的 Credentials 實例。

    Raises:
        GmailAuthError: token 不存在、已失效且無法刷新，或密文無法解密。
    """
    token_file = Path(token_path)
    if not token_file.exists():
        msg = (
            f"Token 檔案不存在：{token_path}。請先執行 OAuth 授權流程產生 token.json。"
        )
        raise GmailAuthError(msg)

    key_manager = _resolve_master_key_manager(manager)
    try:
        token_info = read_token_payload(token_file, key_manager)
    except json.JSONDecodeError as exc:
        # Corrupt/garbled token.json (or undecryptable plaintext-looking JSON).
        # A genuine master.key mismatch raises MasterKeyMismatchError, which is
        # intentionally NOT caught here so the job fails loud with the
        # "restore data/secrets" guidance rather than a misleading re-auth hint.
        msg = (
            f"Token 檔案無法解析：{token_path}。"
            "請刪除 token.json 後重新執行 OAuth 授權流程。"
        )
        raise GmailAuthError(msg) from exc

    creds = Credentials.from_authorized_user_info(token_info, list(GMAIL_SCOPES))

    if creds.valid:
        return creds

    if not creds.expired or not creds.refresh_token:
        msg = "Token 無效且無法刷新。請刪除 token.json 後重新執行 OAuth 授權流程。"
        raise GmailAuthError(msg)

    try:
        creds.refresh(Request())
        logger.info("Gmail OAuth token 已自動刷新")
    except RefreshError as exc:
        msg = (
            f"Gmail OAuth token 刷新失敗：{exc}。"
            "請刪除 token.json 後重新執行 OAuth 授權流程。"
        )
        raise GmailAuthError(msg) from exc

    # 刷新成功後回寫 **加密** token 檔案，避免下次刷新再度明文化。
    write_encrypted_token_file(token_file, creds.to_json(), key_manager)

    return creds
