"""結構化日誌模組。

提供 JSON 格式輸出、機敏資訊遮罩過濾器、以及集中式日誌設定入口。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccas.config import Settings

# 機敏資訊遮罩正則：OAuth token、密碼、credentials 路徑
_REDACT_PATTERNS: list[re.Pattern[str]] = [
    # Bearer / OAuth token values
    re.compile(r"(bearer\s+)\S+", re.IGNORECASE),
    re.compile(
        r'("?(?:access_token|refresh_token|token)"?\s*[:=]\s*"?)\S+',
        re.IGNORECASE,
    ),
    # password / secret values
    re.compile(
        r'("?(?:password|passwd|secret|api_key|api_secret)'
        r'"?\s*[:=]\s*"?)\S+',
        re.IGNORECASE,
    ),
    # API / bot token values. Defence-in-depth in addition to
    # ``Settings.api_token`` / ``Settings.telegram_bot_token`` being
    # ``SecretStr``: masks ``api_token=...`` / ``API_TOKEN=...`` /
    # ``bot_token=...`` / ``telegram_bot_token=...`` if they ever reach a
    # log line (e.g. a Settings dump or an env echo).
    re.compile(
        r'("?(?:api_token|telegram_bot_token|bot_token)"?\s*[:=]\s*"?)\S+',
        re.IGNORECASE,
    ),
    # credentials file paths
    re.compile(
        r'("?(?:credentials_path|token_path|gmail_credentials_path'
        r'|gmail_token_path)"?\s*[:=]\s*"?)[^\s,"]+',
        re.IGNORECASE,
    ),
    # Taiwanese national ID (1 letter + 9 digits). Trailing \b prevents
    # a longer digit suffix from leaking.
    re.compile(
        r'("?(?:national_id|nid)"?\s*[:=]\s*"?)[A-Z]\d{9}\b',
        re.IGNORECASE,
    ),
    # ROC 民國生日 (7 digits YYYMMDD). Trailing \b avoids partial match
    # on 8-digit Gregorian dates leaking a digit.
    re.compile(
        r'("?(?:roc_birthday|birthday)"?\s*[:=]\s*"?)\d{7}\b',
        re.IGNORECASE,
    ),
    # Card last 4 digits. Trailing \b prevents partial leak when the
    # value is longer than 4 digits.
    re.compile(
        r'("?(?:card_last4|卡號末四碼)"?\s*[:=]\s*"?)\d{4}\b',
        re.IGNORECASE,
    ),
    # Telegram chat_id (6+ digits, optional leading - for group chats).
    re.compile(
        r'("?(?:chat_id|telegram_chat_id)"?\s*[:=]\s*"?)-?\d{6,}\b',
        re.IGNORECASE,
    ),
    # Bare Anthropic API key prefix. Catches ``sk-ant-api03-...`` tokens
    # that appear in SDK exception messages or log lines even when the
    # usual ``api_key=`` keyword is absent. Defence-in-depth in addition
    # to ``Settings.anthropic_api_key`` being a ``SecretStr``.
    re.compile(r"(sk-ant-api\d{2}-)[A-Za-z0-9_-]+"),
    # Session cookie value in Cookie / Set-Cookie header dumps. Keyed on
    # the cookie name so attributes after ``;`` (HttpOnly, Max-Age…) stay
    # readable. The name mirrors ``Settings.api_session_cookie_name``'s
    # default; log.py must not import ccas.config at module level (circular
    # import), so the literal is duplicated here intentionally.
    re.compile(r"(\bccas_session=)[^;\s\"']+", re.IGNORECASE),
    # Fallback for the session token *structure* (version.timestamp.hmac-hex),
    # so the value stays masked even if API_SESSION_COOKIE_NAME is overridden
    # and no longer matches the name-keyed pattern above. {9,13} also covers a
    # future millisecond timestamp; the hex part must stay lowercase (matches
    # hexdigest() output — revisit if the encoder ever upper-cases it).
    re.compile(r"()\b\d+\.\d{9,13}\.[0-9a-f]{64}\b"),
    # Raw JWT values keyed by ``jwt`` / ``authorization``. Covers
    # FUBON's raw ``Authorization`` header (no Bearer prefix) and
    # ``"jwt": "..."`` fields in logged JSON bodies. The 4-char segment
    # minimum avoids matching short version strings like "1.2.3".
    re.compile(
        r'("?(?:jwt|authorization)"?\s*[:=]\s*"?)'
        r"[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}",
        re.IGNORECASE,
    ),
    # PDF password env-style assignments (PDF_PASSWORD_CTBC=secret). The
    # generic password rule above requires ":" or "=" right after the word
    # "password", so bank-suffixed env names slip through without this.
    re.compile(r"(PDF_PASSWORD_[A-Z0-9_]+\s*=\s*)\S+", re.IGNORECASE),
]

_REDACT_REPLACEMENT = r"\g<1>[REDACTED]"


class JsonFormatter(logging.Formatter):
    """輸出 JSON 格式日誌。

    包含 timestamp、level、logger、message 欄位。
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC)
        log_entry = {
            "timestamp": ts.isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


class RedactingFilter(logging.Filter):
    """在日誌輸出前遮罩機敏資訊。

    掃描 log record 的 msg 與 args，
    將符合機敏模式的值替換為 [REDACTED]。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def _redact(text: str) -> str:
    """對文字套用所有遮罩規則。"""
    result = text
    for pattern in _REDACT_PATTERNS:
        result = pattern.sub(_REDACT_REPLACEMENT, result)
    return result


def configure_logging(settings: Settings | None = None) -> None:
    """依 Settings 設定初始化 root logger。

    Args:
        settings: 應用程式設定。若為 None 則使用預設值。
    """
    if settings is None:
        from ccas.config import get_settings

        settings = get_settings()

    level_name = settings.log_level.upper()
    log_format = settings.log_format

    root = logging.getLogger()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # 移除既有 handler 避免重複
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()

    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    # 掛載 RedactingFilter
    handler.addFilter(RedactingFilter())

    root.addHandler(handler)

    # 當 log_dir 非空時，同時寫入檔案
    if settings.log_dir:
        log_path = Path(settings.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / f"{settings.log_file_prefix}.log",
            maxBytes=settings.log_file_max_bytes,
            backupCount=settings.log_file_backup_count,
        )
        file_handler.setFormatter(handler.formatter)
        file_handler.addFilter(RedactingFilter())
        root.addHandler(file_handler)
