"""Unit tests for ``ccas.ingestor.gmail_connection`` (framework-free)。

Uses in-memory port implementations so the OAuth business logic is tested
without FastAPI, httpx, or a real DB session.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ccas.ingestor.gmail_connection import (
    AuthorizeError,
    AuthorizeResult,
    CallbackKind,
    GmailConnectionService,
    GmailOAuthConfig,
    OAuthStateRecord,
    TokenExchange,
    UploadError,
    UploadResult,
)

_CLIENT_ID = "1234567890-abc.apps.googleusercontent.com"
_CLIENT_SECRET = "GOCSPX-test-secret"  # noqa: S105


def _valid_credentials_payload() -> dict[str, Any]:
    return {
        "web": {
            "client_id": _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
            "redirect_uris": ["http://localhost:8080/setup/gmail/callback"],
        }
    }


class InMemoryCredentialFile:
    """In-memory ``CredentialFilePort``."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload
        self.raise_on_load: Exception | None = None

    def exists(self) -> bool:
        return self._payload is not None

    def load(self) -> dict[str, Any]:
        if self.raise_on_load is not None:
            raise self.raise_on_load
        assert self._payload is not None
        return self._payload

    def save(self, payload: dict[str, Any]) -> str:
        self._payload = payload
        return "/data/credentials.json"


class InMemoryTokenStore:
    """In-memory ``TokenStorePort``."""

    def __init__(self) -> None:
        self._payload: dict[str, Any] | None = None
        self.write_raises: Exception | None = None
        # Simulates a token file present on disk but undecryptable/corrupt:
        # exists() -> True while read() -> None (adapter-level "not connected"
        # translation), distinct from "no file at all".
        self.corrupt = False
        self.delete_calls = 0

    def exists(self) -> bool:
        return self._payload is not None or self.corrupt

    def read(self) -> dict[str, Any] | None:
        if self.corrupt:
            return None
        return self._payload

    def write(self, payload: dict[str, Any]) -> None:
        if self.write_raises is not None:
            raise self.write_raises
        self._payload = payload

    def delete(self) -> None:
        self.delete_calls += 1
        self._payload = None
        self.corrupt = False


class InMemoryStateStore:
    """In-memory ``OAuthStateStorePort``."""

    def __init__(self) -> None:
        self._rows: dict[str, OAuthStateRecord] = {}

    async def add(self, record: OAuthStateRecord) -> None:
        self._rows[record.state] = record

    async def get(self, state: str) -> OAuthStateRecord | None:
        return self._rows.get(state)

    async def delete(self, state: str) -> None:
        self._rows.pop(state, None)


class FakeGoogleOAuth:
    """In-memory ``GoogleOAuthPort``."""

    def __init__(self) -> None:
        self.exchange_result = TokenExchange(
            ok=True,
            token={
                "access_token": "ya29.fake-access",  # noqa: S106
                "refresh_token": "1//fake-refresh",  # noqa: S106
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            },
        )
        self.email_result: str | None = "alice@example.com"
        self.revoked_tokens: list[str] = []

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        verifier: str,
        redirect_uri: str,
    ) -> TokenExchange:
        return self.exchange_result

    async def fetch_email(self, access_token: str) -> str | None:
        return self.email_result

    async def revoke(self, token: str) -> None:
        self.revoked_tokens.append(token)


def _make_service(
    *,
    credentials: InMemoryCredentialFile | None = None,
    tokens: InMemoryTokenStore | None = None,
    states: InMemoryStateStore | None = None,
    google: FakeGoogleOAuth | None = None,
    now: datetime | None = None,
) -> tuple[
    GmailConnectionService,
    InMemoryCredentialFile,
    InMemoryTokenStore,
    InMemoryStateStore,
    FakeGoogleOAuth,
]:
    credentials = credentials if credentials is not None else InMemoryCredentialFile()
    tokens = tokens if tokens is not None else InMemoryTokenStore()
    states = states if states is not None else InMemoryStateStore()
    google = google if google is not None else FakeGoogleOAuth()
    config = GmailOAuthConfig(
        redirect_uri="http://localhost:8080/setup/gmail/callback",
        scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        state_ttl=timedelta(minutes=10),
        token_uri="https://oauth2.googleapis.com/token",
    )
    clock = now if now is not None else datetime.now(UTC)
    service = GmailConnectionService(
        credentials=credentials,
        tokens=tokens,
        states=states,
        google=google,
        config=config,
        now=lambda: clock,
    )
    return service, credentials, tokens, states, google


# ---------------------------------------------------------------------------
# prepare_upload
# ---------------------------------------------------------------------------


class TestPrepareUpload:
    def test_valid_payload_saves_and_returns_client_id_last8(self) -> None:
        service, credentials, *_ = _make_service()
        result = service.prepare_upload(
            json.dumps(_valid_credentials_payload()).encode()
        )
        assert isinstance(result, UploadResult)
        assert result.saved_path == "/data/credentials.json"
        assert result.client_id_last8 == _CLIENT_ID[-8:]
        assert credentials.exists()

    def test_oversized_rejected(self) -> None:
        service, *_ = _make_service()
        result = service.prepare_upload(b"x" * 1_000_001)
        assert result is UploadError.OVERSIZED

    def test_not_json_rejected(self) -> None:
        service, *_ = _make_service()
        result = service.prepare_upload(b"not json")
        assert result is UploadError.NOT_JSON

    def test_not_object_rejected(self) -> None:
        service, *_ = _make_service()
        result = service.prepare_upload(b"[1, 2, 3]")
        assert result is UploadError.NOT_OBJECT

    def test_missing_block_rejected(self) -> None:
        service, *_ = _make_service()
        result = service.prepare_upload(json.dumps({"foo": "bar"}).encode())
        assert result is UploadError.MISSING_BLOCK

    def test_missing_client_secret_rejected(self) -> None:
        service, *_ = _make_service()
        payload = {"web": {"client_id": "abc.apps.googleusercontent.com"}}
        result = service.prepare_upload(json.dumps(payload).encode())
        assert result is UploadError.MISSING_CLIENT


# ---------------------------------------------------------------------------
# authorize
# ---------------------------------------------------------------------------


class TestAuthorize:
    async def test_ok_returns_url_and_persists_state(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        service, _creds, _tokens, states, _google = _make_service(
            credentials=credentials
        )
        result = await service.authorize()
        assert isinstance(result, AuthorizeResult)
        assert result.authorize_url.startswith(
            "https://accounts.google.com/o/oauth2/v2/auth?"
        )
        assert "code_challenge=" in result.authorize_url
        assert "code_challenge_method=S256" in result.authorize_url
        stored = await states.get(result.state)
        assert stored is not None
        assert stored.code_verifier

    async def test_no_credentials_returns_error(self) -> None:
        service, *_ = _make_service()
        result = await service.authorize()
        assert result is AuthorizeError.NO_CREDENTIALS

    async def test_invalid_credentials_returns_error(self) -> None:
        credentials = InMemoryCredentialFile({"foo": "bar"})
        service, *_ = _make_service(credentials=credentials)
        result = await service.authorize()
        assert result is AuthorizeError.INVALID_CREDENTIALS


# ---------------------------------------------------------------------------
# handle_callback
# ---------------------------------------------------------------------------


class TestHandleCallback:
    async def test_connected_writes_token_including_email(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        states = InMemoryStateStore()
        now = datetime.now(UTC)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=now)
        )
        service, _creds, tokens, _states, google = _make_service(
            credentials=credentials, states=states, now=now
        )
        outcome = await service.handle_callback(
            code="auth-code", state="s1", error=None
        )
        assert outcome.kind is CallbackKind.CONNECTED
        assert outcome.email == "alice@example.com"
        stored = tokens.read()
        assert stored is not None
        assert stored["token"] == "ya29.fake-access"  # noqa: S105
        assert stored["refresh_token"] == "1//fake-refresh"  # noqa: S105
        assert stored["email"] == "alice@example.com"
        # State consumed.
        assert await states.get("s1") is None

    async def test_oauth_error_short_circuits(self) -> None:
        service, *_ = _make_service()
        outcome = await service.handle_callback(
            code=None, state=None, error="access_denied"
        )
        assert outcome.kind is CallbackKind.OAUTH_ERROR

    async def test_missing_code_or_state(self) -> None:
        service, *_ = _make_service()
        outcome = await service.handle_callback(code=None, state="s1", error=None)
        assert outcome.kind is CallbackKind.MISSING_CODE

    async def test_unknown_state(self) -> None:
        service, *_ = _make_service()
        outcome = await service.handle_callback(
            code="c", state="nonexistent", error=None
        )
        assert outcome.kind is CallbackKind.UNKNOWN_STATE

    async def test_expired_state(self) -> None:
        states = InMemoryStateStore()
        old = datetime.now(UTC) - timedelta(hours=1)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=old)
        )
        now = datetime.now(UTC)
        service, *_ = _make_service(states=states, now=now)
        outcome = await service.handle_callback(code="c", state="s1", error=None)
        assert outcome.kind is CallbackKind.EXPIRED_STATE
        # State deleted even on expiry.
        assert await states.get("s1") is None

    async def test_exchange_ok_false_maps_to_exchange_failed(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        states = InMemoryStateStore()
        now = datetime.now(UTC)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=now)
        )
        google = FakeGoogleOAuth()
        google.exchange_result = TokenExchange(ok=False)
        service, *_ = _make_service(
            credentials=credentials, states=states, google=google, now=now
        )
        outcome = await service.handle_callback(code="c", state="s1", error=None)
        assert outcome.kind is CallbackKind.EXCHANGE_FAILED
        # State still consumed (deleted before exchange attempt).
        assert await states.get("s1") is None

    async def test_token_write_raise_maps_to_exchange_failed(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        states = InMemoryStateStore()
        now = datetime.now(UTC)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=now)
        )
        tokens = InMemoryTokenStore()
        tokens.write_raises = OSError("disk full")
        service, *_ = _make_service(
            credentials=credentials, states=states, tokens=tokens, now=now
        )
        outcome = await service.handle_callback(code="c", state="s1", error=None)
        assert outcome.kind is CallbackKind.EXCHANGE_FAILED

    async def test_profile_fetch_failure_still_connected_without_email(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        states = InMemoryStateStore()
        now = datetime.now(UTC)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=now)
        )
        google = FakeGoogleOAuth()
        google.email_result = None
        service, _creds, tokens, _states, _google = _make_service(
            credentials=credentials, states=states, google=google, now=now
        )
        outcome = await service.handle_callback(code="c", state="s1", error=None)
        assert outcome.kind is CallbackKind.CONNECTED
        assert outcome.email is None
        stored = tokens.read()
        assert stored is not None
        assert "email" not in stored


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_connected_when_token_present(self) -> None:
        tokens = InMemoryTokenStore()
        tokens.write(
            {
                "token": "ya29.fake",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                "email": "alice@example.com",
            }
        )
        service, *_ = _make_service(tokens=tokens)
        result = service.get_status()
        assert result.connected is True
        assert result.email == "alice@example.com"
        assert result.granted_scopes == [
            "https://www.googleapis.com/auth/gmail.readonly"
        ]

    def test_disconnected_when_token_missing(self) -> None:
        service, *_ = _make_service()
        result = service.get_status()
        assert result.connected is False
        assert result.email is None


# ---------------------------------------------------------------------------
# revoke
# ---------------------------------------------------------------------------


class TestRevoke:
    async def test_deletes_token_and_calls_google(self) -> None:
        tokens = InMemoryTokenStore()
        tokens.write({"token": "ya29.fake-revoke", "refresh_token": "1//fake"})
        google = FakeGoogleOAuth()
        service, _creds, tokens2, _states, google2 = _make_service(
            tokens=tokens, google=google
        )
        result = await service.revoke()
        assert result.connected is False
        assert tokens2.read() is None
        assert google2.revoked_tokens == ["ya29.fake-revoke"]

    async def test_idempotent_without_token(self) -> None:
        service, *_ = _make_service()
        result = await service.revoke()
        assert result.connected is False

    async def test_corrupt_token_file_still_deleted(self) -> None:
        """exists()=True but read()=None (corrupt/undecryptable) must still
        be deleted -- the file must never silently persist."""
        tokens = InMemoryTokenStore()
        tokens.corrupt = True
        google = FakeGoogleOAuth()
        service, _creds, tokens2, _states, google2 = _make_service(
            tokens=tokens, google=google
        )
        result = await service.revoke()
        assert result.connected is False
        assert tokens2.delete_calls == 1
        assert google2.revoked_tokens == []


# ---------------------------------------------------------------------------
# Secret-safety
# ---------------------------------------------------------------------------


class TestSecretSafety:
    async def test_callback_outcome_repr_does_not_leak_secrets(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        states = InMemoryStateStore()
        now = datetime.now(UTC)
        await states.add(
            OAuthStateRecord(state="s1", code_verifier="v1", created_at=now)
        )
        service, *_ = _make_service(credentials=credentials, states=states, now=now)
        outcome = await service.handle_callback(code="c", state="s1", error=None)
        blob = repr(outcome)
        assert "ya29.fake-access" not in blob
        assert "1//fake-refresh" not in blob
        assert _CLIENT_SECRET not in blob

    async def test_authorize_result_repr_does_not_leak_secrets(self) -> None:
        credentials = InMemoryCredentialFile(_valid_credentials_payload())
        service, *_ = _make_service(credentials=credentials)
        result = await service.authorize()
        assert _CLIENT_SECRET not in repr(result)

    def test_upload_result_repr_does_not_leak_secrets(self) -> None:
        service, *_ = _make_service()
        result = service.prepare_upload(
            json.dumps(_valid_credentials_payload()).encode()
        )
        assert _CLIENT_SECRET not in repr(result)

    def test_status_result_repr_does_not_leak_secrets(self) -> None:
        tokens = InMemoryTokenStore()
        tokens.write({"token": "ya29.super-secret-access-token"})
        service, *_ = _make_service(tokens=tokens)
        result = service.get_status()
        assert "ya29.super-secret-access-token" not in repr(result)
