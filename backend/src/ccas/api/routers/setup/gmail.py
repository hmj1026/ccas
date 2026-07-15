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
- credentials.json / token.json 以 master.key Fernet 加密落檔（envelope 格式，
  見 ``ccas.storage.oauth_secrets``）。讀取時自動解密，並向後相容既有 plaintext
  檔（legacy fallback），下一次寫入時升級為密文。client_secret / refresh_token
  不再以明文存放於 ``data/``。

架構取捨（deepen-codebase-architecture）：
- 本檔案只負責「HTTP 轉譯」：建立 production adapters（DB session / 檔案系統 /
  httpx）並把 ``GmailConnectionService`` 的 outcome dataclasses 映射成
  FastAPI response（狀態碼、redirect、錯誤訊息）。所有決策邏輯（PKCE/state
  處理、TTL 檢查、payload 驗證）都在 ``ccas.ingestor.gmail_connection`` 之中，
  該模組framework-free、可脫離 FastAPI/httpx/DB 單元測試。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

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
from ccas.ingestor.auth import GMAIL_SCOPES
from ccas.ingestor.gmail_connection import (
    AuthorizeError,
    CallbackKind,
    GmailConnectionService,
    GmailOAuthConfig,
    OAuthStateRecord,
    TokenExchange,
    UploadError,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import GmailOAuthState
from ccas.storage.oauth_secrets import (
    read_token_payload,
    write_encrypted_token_file,
)
from ccas.storage.secrets import MasterKeyMismatchError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup/gmail", tags=["setup-gmail"])

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Gmail's own getProfile returns ``emailAddress`` under the existing
# ``gmail.readonly`` scope, so no extra OAuth scope / re-consent is needed
# (unlike the generic Google userinfo endpoint, which requires
# ``userinfo.email``). See setup/gmail callback for the non-blocking call.
_GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
_STATE_TTL_MINUTES = 10
_CALLBACK_PATH = "/setup/gmail/callback"
_FRONTEND_RESULT_PATH = "/setup/gmail"


# ---------------------------------------------------------------------------
# Production adapters (ports implemented against real settings/DB/httpx)
# ---------------------------------------------------------------------------


class _CredentialFileAdapter:
    """``CredentialFilePort`` backed by the on-disk encrypted credentials.json."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = Path(settings.gmail_credentials_path)

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> dict[str, Any]:
        return read_token_payload(self._path, self._settings.master_key_manager)

    def save(self, payload: dict[str, Any]) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_encrypted_token_file(
            self._path, json.dumps(payload, indent=2), self._settings.master_key_manager
        )
        return str(self._path)


class _TokenStoreAdapter:
    """``TokenStorePort`` backed by the on-disk encrypted token.json."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = Path(settings.gmail_token_path)

    def exists(self) -> bool:
        return self._path.exists()

    def read(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            return read_token_payload(self._path, self._settings.master_key_manager)
        except (json.JSONDecodeError, MasterKeyMismatchError):
            # Unreadable/undecryptable token.json is treated as "not
            # connected" (status is advisory; the user can re-run the OAuth
            # flow). A master.key mismatch is logged so operators can spot a
            # botched data/ restore.
            logger.warning("Gmail token.json unreadable; reporting disconnected")
            return None

    def write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_encrypted_token_file(
            self._path, json.dumps(payload, indent=2), self._settings.master_key_manager
        )

    def delete(self) -> None:
        self._path.unlink(missing_ok=True)


class _DbOAuthStateStore:
    """``OAuthStateStorePort`` backed by the ``gmail_oauth_state`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: OAuthStateRecord) -> None:
        self._session.add(
            GmailOAuthState(
                state=record.state,
                code_verifier=record.code_verifier,
                created_at=record.created_at,
            )
        )
        await self._session.commit()

    async def get(self, state: str) -> OAuthStateRecord | None:
        row = await self._session.get(GmailOAuthState, state)
        if row is None:
            return None
        return OAuthStateRecord(
            state=row.state, code_verifier=row.code_verifier, created_at=row.created_at
        )

    async def delete(self, state: str) -> None:
        row = await self._session.get(GmailOAuthState, state)
        if row is None:
            return
        await self._session.delete(row)
        await self._session.commit()


class _HttpxGoogleOAuth:
    """``GoogleOAuthPort`` backed by ``httpx.AsyncClient`` calls to Google."""

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        verifier: str,
        redirect_uri: str,
    ) -> TokenExchange:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    _GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code_verifier": verifier,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                )
        except httpx.HTTPError:
            logger.warning("Gmail token exchange request failed", exc_info=True)
            return TokenExchange(ok=False)
        if resp.status_code != 200:
            logger.warning(
                "Gmail token exchange failed: status=%d body_len=%d",
                resp.status_code,
                len(resp.text),
            )
            return TokenExchange(ok=False)
        return TokenExchange(ok=True, token=resp.json())

    async def fetch_email(self, access_token: str) -> str | None:
        """Best-effort fetch of the connected mailbox address via Gmail getProfile.

        Uses the existing ``gmail.readonly`` scope (no extra consent). Any
        failure (network, non-200, malformed body) is swallowed and returns
        ``None`` — the address is advisory and must never block the OAuth
        callback.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.get(
                    _GMAIL_PROFILE_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError:
            logger.warning("Gmail getProfile request failed", exc_info=True)
            return None
        if resp.status_code != 200:
            logger.warning("Gmail getProfile returned status=%d", resp.status_code)
            return None
        try:
            email = resp.json().get("emailAddress")
        except (ValueError, UnicodeDecodeError):
            # Malformed/odd-encoding body — advisory only, never block the callback.
            logger.warning("Gmail getProfile returned non-JSON body")
            return None
        return email if isinstance(email, str) and email else None

    async def revoke(self, token: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                revoke_resp = await http.post(
                    _GOOGLE_REVOKE_URL,
                    data={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            # Best-effort: log non-2xx responses from Google. We still delete
            # the local token (the revoke call is advisory; the local file is
            # the authoritative record of "we no longer use this token").
            # Operators may need to revoke manually at
            # https://myaccount.google.com/permissions if the remote revoke
            # failed.
            if revoke_resp.status_code >= 400:
                logger.warning(
                    "Gmail revoke endpoint returned non-2xx: status=%d",
                    revoke_resp.status_code,
                )
        except httpx.HTTPError as exc:
            logger.warning("Gmail revoke remote call failed: %s", exc)


class _NullStateStore:
    """No-op ``OAuthStateStorePort`` for endpoints that never touch state.

    ``upload_credentials`` / ``status`` / ``revoke`` don't take a DB session
    dependency; wiring a real ``_DbOAuthStateStore`` for them would require
    one just to satisfy the service constructor. Any accidental call is a
    programming error, so it fails loudly rather than silently no-op'ing.
    """

    async def add(self, record: OAuthStateRecord) -> None:
        raise NotImplementedError("state store not wired for this endpoint")

    async def get(self, state: str) -> OAuthStateRecord | None:
        raise NotImplementedError("state store not wired for this endpoint")

    async def delete(self, state: str) -> None:
        raise NotImplementedError("state store not wired for this endpoint")


def _build_service(
    settings: Settings, session: AsyncSession | None = None
) -> GmailConnectionService:
    """Build a :class:`GmailConnectionService` wired to production adapters.

    *session* is required for the ``authorize``/``callback`` endpoints (which
    read/write ``gmail_oauth_state``); the other endpoints never touch OAuth
    state and pass ``None``, wiring a :class:`_NullStateStore` instead.
    """
    redirect_uri = f"{settings.get_public_base_url()}{_CALLBACK_PATH}"
    config = GmailOAuthConfig(
        redirect_uri=redirect_uri,
        scopes=GMAIL_SCOPES,
        state_ttl=timedelta(minutes=_STATE_TTL_MINUTES),
        token_uri=_GOOGLE_TOKEN_URL,
    )
    states = _DbOAuthStateStore(session) if session is not None else _NullStateStore()
    return GmailConnectionService(
        credentials=_CredentialFileAdapter(settings),
        tokens=_TokenStoreAdapter(settings),
        states=states,
        google=_HttpxGoogleOAuth(),
        config=config,
    )


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
    """Upload Google OAuth ``credentials.json``, encrypt, persist 0600."""
    raw = await file.read()
    service = _build_service(settings)
    result = service.prepare_upload(raw)
    if result is UploadError.OVERSIZED:
        raise HTTPException(
            status_code=413, detail="檔案過大，credentials.json 應小於 1 MB"
        )
    if result is UploadError.NOT_JSON:
        raise HTTPException(status_code=422, detail="上傳檔案不是合法 JSON")
    if result is UploadError.NOT_OBJECT:
        raise HTTPException(status_code=422, detail="credentials.json 頂層必須為物件")
    if result is UploadError.MISSING_BLOCK:
        raise HTTPException(
            status_code=422,
            detail="credentials.json 必須包含 'web' 或 'installed' 物件",
        )
    if result is UploadError.MISSING_CLIENT:
        raise HTTPException(
            status_code=422, detail="credentials.json 缺少 client_id 或 client_secret"
        )

    return ApiResponse(
        data=GmailCredentialsUploadResult(
            saved_path=result.saved_path,
            client_id_last8=result.client_id_last8,
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
    service = _build_service(settings, session)
    result = await service.authorize()
    if result is AuthorizeError.NO_CREDENTIALS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Gmail credentials.json 尚未上傳；"
                "請先呼叫 POST /api/setup/gmail/credentials"
            ),
        )
    if result is AuthorizeError.INVALID_CREDENTIALS:
        raise HTTPException(
            status_code=422,
            detail="credentials.json 解析失敗（格式不正確）",
        )

    return ApiResponse(
        data=GmailAuthorizeUrl(authorize_url=result.authorize_url, state=result.state)
    )


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Exchange ``code`` + stored verifier for tokens; write token.json.

    ``code`` / ``state`` are optional so the user-denied redirect (which carries
    ``error`` instead of ``code``) reaches this handler rather than tripping
    FastAPI's required-parameter validation (422).
    """
    service = _build_service(settings, session)
    outcome = await service.handle_callback(code=code, state=state, error=error)

    if outcome.kind is CallbackKind.MISSING_CODE:
        raise HTTPException(
            status_code=400,
            detail="OAuth callback 缺少 code 或 state",
        )
    if outcome.kind is CallbackKind.UNKNOWN_STATE:
        raise HTTPException(status_code=422, detail="未知或已使用的 OAuth state")
    if outcome.kind is CallbackKind.EXPIRED_STATE:
        raise HTTPException(
            status_code=422,
            detail="OAuth state 已過期，請重新點擊授權按鈕",
        )
    if outcome.kind in (CallbackKind.OAUTH_ERROR, CallbackKind.EXCHANGE_FAILED):
        return RedirectResponse(
            url=f"{_FRONTEND_RESULT_PATH}?status=error", status_code=303
        )

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
    service = _build_service(settings)
    result = service.get_status()
    return ApiResponse(
        data=GmailConnectionStatus(
            connected=result.connected,
            email=result.email,
            granted_scopes=result.granted_scopes,
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
    service = _build_service(settings)
    result = await service.revoke()
    return ApiResponse(
        data=GmailConnectionStatus(
            connected=result.connected,
            email=result.email,
            granted_scopes=result.granted_scopes,
        )
    )
