"""Gmail OAuth 憑證載入與 token 自動刷新。

負責從本地 token 檔案載入已授權的 OAuth 憑證，
並在 access token 過期時自動刷新。
"""

import logging
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ccas.errors import IngestError

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


def write_private_token_file(path: Path, content: str) -> None:
    """寫入 token 檔並收斂權限到 owner-only。"""
    path.write_text(content)
    path.chmod(0o600)


class GmailAuthError(IngestError):
    """Gmail OAuth 驗證失敗。"""

    def __init__(self, reason: str = "", **ctx: object) -> None:
        super().__init__("Gmail OAuth 驗證失敗", reason=reason, **ctx)


def load_credentials(credentials_path: str, token_path: str) -> Credentials:
    """從 token.json 載入 OAuth Credentials，必要時自動刷新。

    Args:
        credentials_path: OAuth 應用程式憑證 JSON 檔路徑（首次授權時使用）。
        token_path: 授權後保存的 token JSON 檔路徑。

    Returns:
        有效的 Credentials 實例。

    Raises:
        GmailAuthError: token 不存在、已失效且無法刷新。
    """
    token_file = Path(token_path)
    if not token_file.exists():
        msg = (
            f"Token 檔案不存在：{token_path}。請先執行 OAuth 授權流程產生 token.json。"
        )
        raise GmailAuthError(msg)

    creds = Credentials.from_authorized_user_file(str(token_file), list(GMAIL_SCOPES))

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

    # 刷新成功後回寫 token 檔案
    write_private_token_file(token_file, creds.to_json())

    return creds
