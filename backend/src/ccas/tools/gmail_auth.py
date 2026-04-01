"""產生或更新本地 Gmail OAuth token。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from ccas.config import get_settings
from ccas.ingestor.auth import GMAIL_SCOPES


class GmailAuthSetupError(ValueError):
    """Gmail OAuth 前置檢查失敗。"""


@dataclass(frozen=True)
class AuthPaths:
    """OAuth 所需的檔案路徑。"""

    credentials_path: Path
    token_path: Path


def resolve_auth_paths(
    credentials_path: str | Path, token_path: str | Path
) -> AuthPaths:
    """確認 credentials 路徑存在並回傳標準化路徑。"""
    credentials = Path(credentials_path)
    token = Path(token_path)

    if not credentials.exists():
        raise GmailAuthSetupError(
            "找不到 Gmail OAuth credentials 檔案："
            f"{credentials}。"
            "請先確認 GMAIL_CREDENTIALS_PATH 指向正確的 credentials.json。"
        )

    return AuthPaths(credentials_path=credentials, token_path=token)


def should_generate_token(paths: AuthPaths, *, force: bool) -> bool:
    """判斷是否需要重新產生 token。"""
    return force or not paths.token_path.exists()


def generate_token(paths: AuthPaths) -> Path:
    """執行 Gmail OAuth 授權並寫入 token 檔。"""
    flow = InstalledAppFlow.from_client_secrets_file(
        str(paths.credentials_path), list(GMAIL_SCOPES)
    )
    creds = flow.run_local_server(port=0)
    paths.token_path.parent.mkdir(parents=True, exist_ok=True)
    paths.token_path.write_text(creds.to_json(), encoding="utf-8")
    return paths.token_path


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="產生本地 Gmail token.json。")
    parser.add_argument(
        "--credentials",
        default=settings.gmail_credentials_path,
        help="credentials.json 路徑",
    )
    parser.add_argument(
        "--token",
        default=settings.gmail_token_path,
        help="token.json 路徑",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使 token 已存在也重新授權覆蓋。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        paths = resolve_auth_paths(args.credentials, args.token)
    except GmailAuthSetupError as exc:
        print(f"[ERROR] {exc}")
        return 2

    if not should_generate_token(paths, force=args.force):
        print(
            f"[SKIP] token 已存在：{paths.token_path}。若要重新授權，請加上 --force。"
        )
        return 0

    token_path = generate_token(paths)
    print(f"[OK] token 已寫入：{token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
