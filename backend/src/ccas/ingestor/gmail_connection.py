"""Framework-free Gmail OAuth connection service (deepen-codebase-architecture).

Extracted from ``ccas.api.routers.setup.gmail`` so the OAuth business logic
(upload validation, PKCE/state handling, token exchange orchestration, status
derivation, revoke) can be unit-tested without FastAPI, httpx, or a real DB
session. The router becomes a thin translator: it builds the production
adapters (DB session, filesystem, httpx) and maps :class:`GmailConnectionService`
outcomes onto HTTP responses.

This module MUST NOT import FastAPI, httpx, or SQLAlchemy — it only depends on
``typing.Protocol``-based ports so tests can supply in-memory fakes.

Outcome dataclasses are intentionally secret-safe: they never carry access
tokens, refresh tokens, client secrets, or ciphertext. Callers needing the
actual credentials must go through the ports directly.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import Any, Protocol
from urllib.parse import urlencode

from ccas.storage.secrets import MasterKeyMismatchError

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class CredentialFilePort(Protocol):
    """Access to the encrypted ``credentials.json`` file."""

    def exists(self) -> bool:
        """Return True if a credentials file has been uploaded."""
        ...

    def load(self) -> dict[str, Any]:
        """Load (decrypt) the credentials payload.

        Raises:
            json.JSONDecodeError: content is not valid JSON.
        """
        ...

    def save(self, payload: dict[str, Any]) -> str:
        """Persist *payload* (encrypted); return the saved path as a string."""
        ...


class TokenStorePort(Protocol):
    """Access to the encrypted ``token.json`` file."""

    def exists(self) -> bool:
        """Return True if a token file is present on disk."""
        ...

    def read(self) -> dict[str, Any] | None:
        """Read the token payload.

        Unreadable/undecryptable content is the adapter's responsibility to
        translate into ``None`` (advisory "not connected" semantics) rather
        than raising here.
        """
        ...

    def write(self, payload: dict[str, Any]) -> None:
        """Persist *payload* (encrypted, 0600)."""
        ...

    def delete(self) -> None:
        """Remove the token file if present (idempotent)."""
        ...


@dataclasses.dataclass(frozen=True, slots=True)
class OAuthStateRecord:
    """A persisted PKCE state row."""

    state: str
    code_verifier: str
    created_at: datetime


class OAuthStateStorePort(Protocol):
    """Access to the ``gmail_oauth_state`` persistence."""

    async def add(self, record: OAuthStateRecord) -> None:
        """Persist a new state row."""
        ...

    async def get(self, state: str) -> OAuthStateRecord | None:
        """Fetch a state row by its token, or None if unknown."""
        ...

    async def delete(self, state: str) -> None:
        """Remove a state row (idempotent)."""
        ...


@dataclasses.dataclass(frozen=True, slots=True)
class TokenExchange:
    """Result of exchanging an authorization code for tokens."""

    ok: bool
    token: dict[str, Any] | None = None


class GoogleOAuthPort(Protocol):
    """Network calls against Google's OAuth / Gmail endpoints."""

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        verifier: str,
        redirect_uri: str,
    ) -> TokenExchange:
        """Exchange an authorization code for an access/refresh token pair."""
        ...

    async def fetch_email(self, access_token: str) -> str | None:
        """Best-effort fetch of the connected mailbox address."""
        ...

    async def revoke(self, token: str) -> None:
        """Best-effort revoke of an access/refresh token."""
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class GmailOAuthConfig:
    """Wiring configuration for :class:`GmailConnectionService`."""

    redirect_uri: str
    scopes: tuple[str, ...]
    state_ttl: timedelta
    token_uri: str


# ---------------------------------------------------------------------------
# Outcome dataclasses (secret-safe: never carry tokens/client_secret/ciphertext)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class UploadResult:
    """Successful ``credentials.json`` upload outcome."""

    saved_path: str
    client_id_last8: str


class UploadError(Enum):
    """Reasons ``prepare_upload`` can fail."""

    OVERSIZED = auto()
    NOT_JSON = auto()
    NOT_OBJECT = auto()
    MISSING_BLOCK = auto()  # no 'web' or 'installed' object
    MISSING_CLIENT = auto()  # block present but client_id/secret missing/invalid


@dataclasses.dataclass(frozen=True, slots=True)
class AuthorizeResult:
    """Successful ``authorize()`` outcome."""

    authorize_url: str
    state: str


class AuthorizeError(Enum):
    """Reasons ``authorize()`` can fail."""

    NO_CREDENTIALS = auto()
    INVALID_CREDENTIALS = auto()


class CallbackKind(Enum):
    """Discriminator for ``handle_callback`` outcomes."""

    CONNECTED = auto()
    OAUTH_ERROR = auto()
    EXCHANGE_FAILED = auto()
    MISSING_CODE = auto()
    UNKNOWN_STATE = auto()
    EXPIRED_STATE = auto()


@dataclasses.dataclass(frozen=True, slots=True)
class CallbackOutcome:
    """Result of ``handle_callback``."""

    kind: CallbackKind
    email: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ConnectionStatus:
    """Result of ``get_status`` / ``revoke``."""

    connected: bool
    email: str | None = None
    granted_scopes: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GmailConnectionService:
    """Gmail OAuth Web flow business logic, decoupled from FastAPI/httpx/DB.

    All I/O is delegated to the port protocols supplied at construction time;
    this class contains only the decision logic (validation, PKCE/state
    handling, TTL checks, translation of raw payloads into outcome
    dataclasses).
    """

    def __init__(
        self,
        credentials: CredentialFilePort,
        tokens: TokenStorePort,
        states: OAuthStateStorePort,
        google: GoogleOAuthPort,
        config: GmailOAuthConfig,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._credentials = credentials
        self._tokens = tokens
        self._states = states
        self._google = google
        self._config = config
        self._now = now

    # -- upload ---------------------------------------------------------

    def prepare_upload(self, raw: bytes) -> UploadResult | UploadError:
        """Validate an uploaded ``credentials.json`` and persist it."""
        if len(raw) > 1_000_000:
            return UploadError.OVERSIZED
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return UploadError.NOT_JSON
        if not isinstance(payload, dict):
            return UploadError.NOT_OBJECT
        extracted = _extract_oauth_client(payload)
        if extracted is None:
            return UploadError.MISSING_BLOCK
        client_id, client_secret = extracted
        if client_id is None or client_secret is None:
            return UploadError.MISSING_CLIENT

        saved_path = self._credentials.save(payload)
        return UploadResult(saved_path=saved_path, client_id_last8=client_id[-8:])

    # -- authorize --------------------------------------------------------

    async def authorize(self) -> AuthorizeResult | AuthorizeError:
        """Generate PKCE + state, persist verifier, return the authorize URL."""
        if not self._credentials.exists():
            return AuthorizeError.NO_CREDENTIALS
        try:
            payload = self._credentials.load()
        except json.JSONDecodeError:
            return AuthorizeError.INVALID_CREDENTIALS
        extracted = _extract_oauth_client(payload)
        client_id = extracted[0] if extracted else None
        if client_id is None or extracted is None or extracted[1] is None:
            return AuthorizeError.INVALID_CREDENTIALS

        verifier, challenge = _gen_pkce()
        state_token = secrets.token_urlsafe(32)
        await self._states.add(
            OAuthStateRecord(
                state=state_token,
                code_verifier=verifier,
                created_at=self._now(),
            )
        )

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": " ".join(self._config.scopes),
            "state": state_token,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
        return AuthorizeResult(authorize_url=url, state=state_token)

    # -- callback -----------------------------------------------------------

    async def handle_callback(
        self,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> CallbackOutcome:
        """Exchange ``code`` + stored verifier for tokens; persist token.json."""
        if error:
            safe_error = error.replace("\r", "").replace("\n", "")[:200]
            logger.warning("OAuth error from Google: %s", safe_error)
            return CallbackOutcome(kind=CallbackKind.OAUTH_ERROR)
        if not code or not state:
            return CallbackOutcome(kind=CallbackKind.MISSING_CODE)

        record = await self._states.get(state)
        if record is None:
            return CallbackOutcome(kind=CallbackKind.UNKNOWN_STATE)

        created_at = record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if self._now() - created_at > self._config.state_ttl:
            await self._states.delete(state)
            return CallbackOutcome(kind=CallbackKind.EXPIRED_STATE)

        verifier = record.code_verifier
        # NOTE: an unreadable/invalid credentials.json at this point is an
        # untested edge case (the happy path only reaches here after a prior
        # successful ``authorize()``); it is folded into EXCHANGE_FAILED
        # rather than a dedicated 422 to keep CallbackKind to the six
        # documented variants.
        try:
            payload = self._credentials.load()
            extracted = _extract_oauth_client(payload)
        except json.JSONDecodeError:
            extracted = None
        client_id, client_secret = extracted if extracted else (None, None)
        if client_id is None or client_secret is None:
            await self._states.delete(state)
            return CallbackOutcome(kind=CallbackKind.EXCHANGE_FAILED)

        # Consume the state before the (slow) network exchange so it cannot be
        # replayed concurrently while the token exchange is in flight. PKCE
        # (code_verifier) remains the primary protection; a failed exchange
        # then requires the user to restart authorization.
        await self._states.delete(state)

        exchange = await self._google.exchange_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            verifier=verifier,
            redirect_uri=self._config.redirect_uri,
        )
        if not exchange.ok or exchange.token is None:
            return CallbackOutcome(kind=CallbackKind.EXCHANGE_FAILED)
        token = exchange.token

        if not token.get("refresh_token"):
            # Without a refresh token the ingestor cannot renew access later;
            # surface it for operators (prompt=consent should normally
            # guarantee one).
            logger.warning(
                "Google 未回傳 refresh_token；token 將無法自動更新，請重新授權"
            )

        access_token = token.get("access_token")
        email = await self._google.fetch_email(access_token) if access_token else None

        token_record: dict[str, Any] = {
            "token": access_token,
            "refresh_token": token.get("refresh_token"),
            "token_uri": self._config.token_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": token.get("scope", "").split() or list(self._config.scopes),
        }
        if email:
            token_record["email"] = email

        try:
            self._tokens.write(token_record)
        except (MasterKeyMismatchError, OSError):
            logger.error("寫入 Gmail token 檔失敗", exc_info=True)
            return CallbackOutcome(kind=CallbackKind.EXCHANGE_FAILED)

        return CallbackOutcome(kind=CallbackKind.CONNECTED, email=email)

    # -- status / revoke ------------------------------------------------

    def get_status(self) -> ConnectionStatus:
        """Return whether token.json exists and which scopes were granted."""
        token_data = self._tokens.read()
        if token_data is None:
            return ConnectionStatus(connected=False)

        scopes = token_data.get("scopes")
        if not isinstance(scopes, list):
            scopes = []
        email = token_data.get("email")
        if not isinstance(email, str) or not email:
            email = None
        return ConnectionStatus(
            connected=True, email=email, granted_scopes=list(scopes)
        )

    async def revoke(self) -> ConnectionStatus:
        """Delete local token.json and best-effort revoke it with Google."""
        if self._tokens.exists():
            token_data = self._tokens.read()
            if token_data is not None:
                access_or_refresh = token_data.get("token") or token_data.get(
                    "refresh_token"
                )
                if isinstance(access_or_refresh, str) and access_or_refresh:
                    await self._google.revoke(access_or_refresh)
            # Delete is authoritative regardless of readability: a corrupt or
            # undecryptable token file must not silently persist as if the
            # account were still connected — "stop using it" wins even when
            # the best-effort Google revoke above could not run.
            self._tokens.delete()

        return ConnectionStatus(connected=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_oauth_client(
    payload: dict[str, Any],
) -> tuple[str | None, str | None] | None:
    """Pull (client_id, client_secret) from a web/installed credentials block.

    Returns ``None`` when neither a ``web`` nor ``installed`` object is
    present (distinct 422 message from the case where the block exists but
    lacks valid ``client_id``/``client_secret`` strings, in which case the
    tuple's element(s) are ``None``).
    """
    block = payload.get("web") or payload.get("installed")
    if not isinstance(block, dict):
        return None
    client_id = block.get("client_id")
    client_secret = block.get("client_secret")
    return (
        client_id if isinstance(client_id, str) else None,
        client_secret if isinstance(client_secret, str) else None,
    )


def _gen_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    verifier = secrets.token_urlsafe(64)  # 86 url-safe chars, well within RFC bounds
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


__all__ = [
    "AuthorizeError",
    "AuthorizeResult",
    "CallbackKind",
    "CallbackOutcome",
    "ConnectionStatus",
    "CredentialFilePort",
    "GmailConnectionService",
    "GmailOAuthConfig",
    "GoogleOAuthPort",
    "OAuthStateRecord",
    "OAuthStateStorePort",
    "TokenExchange",
    "TokenStorePort",
    "UploadError",
    "UploadResult",
]
