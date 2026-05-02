"""Gmail OAuth Web flow router（oauth-onboarding-ui §3）。

取代既有 host-side ``python -m ccas.tools.gmail_auth`` CLI；改由瀏覽器完成
完整 OAuth dance：

1. ``POST /api/setup/gmail/credentials``：multipart 上傳 ``credentials.json``
2. ``GET /api/setup/gmail/authorize``：產 PKCE + state 並回 Google authorize URL
3. ``GET /api/setup/gmail/callback``：以 code + verifier 換 token、寫檔、redirect
4. ``GET /api/setup/gmail/status``：回連線狀態（不洩漏 token）
5. ``POST /api/setup/gmail/revoke``：刪 token + 通知 Google revoke

PKCE (RFC 7636) 強制啟用，避免授權 code 攔截攻擊。State 條目儲存於
``gmail_oauth_state`` 表，TTL 10 分鐘；過期或不存在皆 reject。

設計取捨：
- 為何不用 ``google_auth_oauthlib.flow.Flow``？該 SDK 仍以 sync API 為主，
  且其 ``fetch_token`` 使用 requests session；本實作直接以 ``httpx.AsyncClient``
  打 Google OAuth endpoints，可獲得乾淨的 async 路徑、便於用 ``respx`` mock
  整合測試，不需額外 ``run_in_threadpool`` 包裝。
- credentials.json 仍以原始 JSON 形式落檔，沿用既有 ``ingestor/auth.py`` 與
  ``tools/gmail_auth.py`` 的 fallback 路徑（PR-C2 不動該流程）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    GmailAuthorizeUrl,
    GmailConnectionStatus,
    GmailCredentialsUploadResult,
)
from ccas.config import Settings, get_settings
from ccas.ingestor.auth import GMAIL_SCOPES, write_private_token_file
from ccas.storage.database import get_db_session
from ccas.storage.models import GmailOAuthState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup/gmail", tags=["setup-gmail"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_STATE_TTL = timedelta(minutes=10)
_CALLBACK_PATH = "/setup/gmail/callback"
_FRONTEND_RESULT_PATH = "/setup/gmail"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_credentials_payload(settings: Settings) -> dict[str, Any]:
    """Load credentials.json from disk, or raise 400."""
    creds_path = Path(settings.gmail_credentials_path)
    if not creds_path.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                "Gmail credentials.json 尚未上傳；"
                "請先呼叫 POST /api/setup/gmail/credentials"
            ),
        )
    try:
        return json.loads(creds_path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"credentials.json 解析失敗：{exc}",
        ) from exc


def _extract_oauth_client(payload: dict[str, Any]) -> tuple[str, str]:
    """Pull (client_id, client_secret) from web/installed credentials block."""
    block = payload.get("web") or payload.get("installed")
    if not isinstance(block, dict):
        raise HTTPException(
            status_code=422,
            detail="credentials.json 必須包含 'web' 或 'installed' 物件",
        )
    client_id = block.get("client_id")
    client_secret = block.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise HTTPException(
            status_code=422,
            detail="credentials.json 缺少 client_id 或 client_secret",
        )
    return client_id, client_secret


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.get_public_base_url()}{_CALLBACK_PATH}"


def _gen_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    verifier = secrets.token_urlsafe(64)  # 86 url-safe chars, well within RFC bounds
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/credentials",
    response_model=ApiResponse[GmailCredentialsUploadResult],
)
async def upload_credentials(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[GmailCredentialsUploadResult]:
    """Upload Google OAuth ``credentials.json`` and persist with 0600 perms."""
    raw = await file.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"上傳檔案不是合法 JSON：{exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="credentials.json 頂層必須為物件")
    client_id, _ = _extract_oauth_client(payload)

    target = Path(settings.gmail_credentials_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_private_token_file(target, json.dumps(payload, indent=2))

    return ApiResponse(
        data=GmailCredentialsUploadResult(
            saved_path=str(target),
            client_id_last8=client_id[-8:],
        )
    )


@router.get(
    "/authorize",
    response_model=ApiResponse[GmailAuthorizeUrl],
)
async def authorize(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[GmailAuthorizeUrl]:
    """Generate PKCE + state, persist verifier, return Google authorize URL."""
    payload = _load_credentials_payload(settings)
    client_id, _ = _extract_oauth_client(payload)

    verifier, challenge = _gen_pkce()
    state_token = secrets.token_urlsafe(32)
    session.add(
        GmailOAuthState(
            state=state_token,
            code_verifier=verifier,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _redirect_uri(settings),
        "scope": " ".join(GMAIL_SCOPES),
        "state": state_token,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
    return ApiResponse(data=GmailAuthorizeUrl(authorize_url=url, state=state_token))


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Exchange ``code`` + stored verifier for tokens; write token.json."""
    row = await session.get(GmailOAuthState, state)
    if row is None:
        raise HTTPException(status_code=400, detail="未知或已使用的 OAuth state")

    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - created_at > _STATE_TTL:
        await session.delete(row)
        await session.commit()
        raise HTTPException(status_code=400, detail="OAuth state 已過期，請重新授權")

    verifier = row.code_verifier
    payload = _load_credentials_payload(settings)
    client_id, client_secret = _extract_oauth_client(payload)

    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": _redirect_uri(settings),
            },
        )
    if resp.status_code != 200:
        logger.warning(
            "Gmail token exchange failed: status=%d body_len=%d",
            resp.status_code,
            len(resp.text),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Google token exchange 失敗（HTTP {resp.status_code}）",
        )
    token = resp.json()

    # Persist token.json in the format google-auth's
    # Credentials.from_authorized_user_info / from_authorized_user_file expect.
    token_record = {
        "token": token.get("access_token"),
        "refresh_token": token.get("refresh_token"),
        "token_uri": _GOOGLE_TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": token.get("scope", "").split() or list(GMAIL_SCOPES),
    }
    token_path = Path(settings.gmail_token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    write_private_token_file(token_path, json.dumps(token_record, indent=2))

    await session.delete(row)
    await session.commit()

    return RedirectResponse(
        url=f"{_FRONTEND_RESULT_PATH}?status=connected",
        status_code=303,
    )


@router.get(
    "/status",
    response_model=ApiResponse[GmailConnectionStatus],
)
async def status(
    settings: Settings = Depends(get_settings),
) -> ApiResponse[GmailConnectionStatus]:
    """Return whether token.json exists and which scopes were granted."""
    token_path = Path(settings.gmail_token_path)
    if not token_path.exists():
        return ApiResponse(data=GmailConnectionStatus(connected=False))
    try:
        token_data = json.loads(token_path.read_text())
    except json.JSONDecodeError:
        return ApiResponse(data=GmailConnectionStatus(connected=False))

    scopes = token_data.get("scopes")
    if not isinstance(scopes, list):
        scopes = []
    # Email is not in token.json — it is fetchable via Google userinfo but
    # would require an extra network call; left None for PR-C2 (front-end
    # surfaces "connected" without email yet).
    return ApiResponse(
        data=GmailConnectionStatus(
            connected=True, email=None, granted_scopes=list(scopes)
        )
    )


@router.post(
    "/revoke",
    response_model=ApiResponse[GmailConnectionStatus],
)
async def revoke(
    settings: Settings = Depends(get_settings),
) -> ApiResponse[GmailConnectionStatus]:
    """Delete local token.json and best-effort POST to Google's revoke endpoint."""
    token_path = Path(settings.gmail_token_path)
    if token_path.exists():
        try:
            token_data = json.loads(token_path.read_text())
        except json.JSONDecodeError:
            token_data = {}
        access_or_refresh = token_data.get("token") or token_data.get("refresh_token")
        if isinstance(access_or_refresh, str) and access_or_refresh:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    revoke_resp = await http.post(
                        _GOOGLE_REVOKE_URL,
                        data={"token": access_or_refresh},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                # Best-effort: log non-2xx responses from Google. We still
                # delete the local token (the revoke call is advisory; the
                # local file is the authoritative record of "we no longer
                # use this token"). Operators may need to revoke manually
                # at https://myaccount.google.com/permissions if the remote
                # revoke failed.
                if revoke_resp.status_code >= 400:
                    logger.warning(
                        "Gmail revoke endpoint returned non-2xx: status=%d",
                        revoke_resp.status_code,
                    )
            except httpx.HTTPError as exc:
                logger.warning("Gmail revoke remote call failed: %s", exc)
        token_path.unlink(missing_ok=True)

    return ApiResponse(data=GmailConnectionStatus(connected=False))
