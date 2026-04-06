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
    # credentials file paths
    re.compile(
        r'("?(?:credentials_path|token_path|gmail_credentials_path'
        r'|gmail_token_path)"?\s*[:=]\s*"?)[^\s,"]+',
        re.IGNORECASE,
    ),
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
