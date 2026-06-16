"""Admin token rotate router (oauth-onboarding-ui §6).

Two endpoints, both protected by the global ``verify_token`` dependency:

* ``GET /api/setup/admin/token-info`` exposes ``last4`` + ``created_at`` so
  the UI can confirm the operator is looking at the right token slot. The
  full token never appears in the response.
* ``POST /api/setup/admin/token-rotate`` produces a fresh hex token, writes
  it atomically to ``secrets/api-token`` (mode 0600), bumps
  ``secrets/api-token-version``, and returns the new token plaintext exactly
  once. After the response is sent every pre-rotate Bearer header and every
  pre-rotate session cookie become 401, because both validation paths read
  the live file contents on every call.

Atomicity: writes go to ``<path>.tmp`` (created with ``O_EXCL`` + 0600) and
are then ``os.replace``-d into place. This prevents a partially written file
from being read by a concurrent ``current_api_token()`` mid-rotate.
"""

from __future__ import annotations

import asyncio
import logging
import secrets as stdlib_secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from ccas.api.deps import current_api_token, current_api_token_version
from ccas.api.schemas import AdminTokenInfo, AdminTokenRotateResult, ApiResponse
from ccas.config import Settings, get_settings
from ccas.storage.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup/admin", tags=["setup-admin"])

# Serialize concurrent rotate calls so the read-bump-write of api-token-version
# is atomic at the process level. Two concurrent rotates without this lock
# could both observe version N, both write N+1, and one caller's HTTP response
# would carry a token that no longer matches what's on disk
# (security-reviewer H1, oauth-onboarding-ui §6).
_rotate_lock = asyncio.Lock()


def _atomic_write_secret(path: Path, content: str) -> None:
    """Write *content* to *path* atomically with mode 0600.

    Delegates to the shared ``atomic_write_bytes`` temp-then-rename helper,
    which creates a fresh same-directory temp file, writes the bytes, applies
    mode 0600, and ``os.replace``-s it into place. Any concurrent reader sees
    either the prior file or the new file, never a partial write; a crash
    leaves at most a stale temp file (auto-cleaned), never a half-written
    secret.
    """
    atomic_write_bytes(path, content.encode("utf-8"), mode=0o600)


@router.get("/token-info", response_model=ApiResponse[AdminTokenInfo])
async def get_token_info(
    settings: Settings = Depends(get_settings),
) -> ApiResponse[AdminTokenInfo]:
    """Return last 4 chars + version + on-disk mtime of the active token.

    Token, version, and mtime are read under ``_rotate_lock`` so a concurrent
    rotate cannot interleave between the three filesystem reads and produce
    a response that pairs old-token last4 with new-token version.
    """
    async with _rotate_lock:
        token = current_api_token()
        version = current_api_token_version()
        created_at: datetime | None = None
        path = settings.api_token_path
        if path.is_file():
            try:
                created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError as exc:
                logger.warning("api_token_path stat failed: %s", exc)
    last4 = token[-4:] if len(token) >= 4 else token
    return ApiResponse(
        data=AdminTokenInfo(last4=last4, created_at=created_at, version=version)
    )


@router.post("/token-rotate", response_model=ApiResponse[AdminTokenRotateResult])
async def rotate_token(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ApiResponse[AdminTokenRotateResult]:
    """Generate a new hex token, persist it, bump version, return plaintext once.

    The response body carries the plaintext token; ``Cache-Control: no-store``
    is set explicitly so any reverse proxy or CDN does not cache the body
    (security-reviewer H2).
    """
    token_path = settings.api_token_path
    version_path = settings.api_token_version_path

    async with _rotate_lock:
        new_token = stdlib_secrets.token_hex(32)
        new_version = current_api_token_version() + 1

        try:
            _atomic_write_secret(token_path, new_token)
            _atomic_write_secret(version_path, str(new_version))
        except OSError as exc:
            logger.error(
                "token_rotate write failed",
                extra={"path": str(token_path), "error": str(exc)},
            )
            raise HTTPException(
                status_code=500,
                detail="無法寫入 token 檔，請檢查 secrets 目錄權限",
            ) from exc

    logger.info(
        "api_token_rotated",
        extra={"version": new_version, "last4": new_token[-4:]},
    )
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(
        data=AdminTokenRotateResult(
            token=new_token,
            version=new_version,
            last4=new_token[-4:],
        )
    )
