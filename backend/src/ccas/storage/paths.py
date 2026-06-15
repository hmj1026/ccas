"""Pure staging-path computation with path-traversal protection.

These helpers compute and validate filesystem paths under the staging root
without any DB or I/O side effects. They were extracted from
``ccas.ingestor.staging`` so that the decryptor/parser jobs can depend on
path logic without coupling to ingestor-internal DB operations.

The traversal-protection helpers (``_sanitize_bank_code``,
``_sanitize_filename``, ``_ensure_within_root``) and the legacy-absolute
remapping in ``resolve_staged_path`` are preserved byte-for-byte from the
original ingestor implementation; do not relax them without a security review.
"""

import re
from pathlib import Path

_BANK_CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _sanitize_bank_code(bank_code: str) -> str:
    value = bank_code.strip()
    if not value or not _BANK_CODE_RE.fullmatch(value):
        raise ValueError(f"Invalid bank_code: {bank_code}")
    return value


def _sanitize_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").strip()
    basename = normalized.rsplit("/", maxsplit=1)[-1].strip()
    if basename in {"", ".", ".."}:
        raise ValueError(f"Invalid filename: {filename}")
    return basename


def _ensure_within_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path {resolved!r} escapes staging root {root!r}")
    return resolved


def build_staged_path(
    staging_dir: str,
    bank_code: str,
    message_id: str,
    filename: str,
) -> Path:
    """產生 PDF 附件的 staging 落地路徑。

    路徑規則：{staging_dir}/{bank_code}/{message_id[:12]}_{filename}

    Args:
        staging_dir: staging 根目錄。
        bank_code: 銀行代碼（用於子目錄隔離）。
        message_id: Gmail message ID（取前 12 字元避免路徑過長）。
        filename: 原始附件檔名。

    Returns:
        附件的完整 staging 路徑。
    """
    staging_root = Path(staging_dir).resolve()
    safe_bank_code = _sanitize_bank_code(bank_code)
    safe_filename = _sanitize_filename(filename)
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", message_id[:12]) or "message"
    bank_root = staging_root / safe_bank_code
    candidate = bank_root / f"{safe_prefix}_{safe_filename}"
    return _ensure_within_root(candidate, bank_root)


def staged_path_for_storage(staging_dir: str, absolute_path: Path) -> str:
    """Convert absolute staging path to relative for DB storage."""
    staging_root = Path(staging_dir).resolve()
    return str(absolute_path.resolve().relative_to(staging_root))


def resolve_staged_path(staging_dir: str, stored_path: str) -> Path:
    """Resolve a stored staged_path (relative or legacy absolute) to absolute.

    Raises ValueError if the resolved path escapes the staging root.
    """
    staging_root = Path(staging_dir).resolve()
    p = Path(stored_path)
    if p.is_absolute():
        try:
            relative = p.relative_to(staging_root)
        except ValueError:
            parts = p.parts
            seg_dir = parts[-2] if len(parts) >= 2 else None
            seg_file = p.name
            if seg_file in {"", ".", ".."} or (seg_dir and seg_dir in {"", ".", ".."}):
                raise ValueError(
                    f"Legacy path contains traversal components: {stored_path}"
                )
            if seg_dir and not _BANK_CODE_RE.fullmatch(seg_dir):
                raise ValueError(f"Legacy path has invalid bank segment: {stored_path}")
            relative = Path(seg_dir) / seg_file if seg_dir else Path(seg_file)
    else:
        relative = p
    resolved = (staging_root / relative).resolve()
    resolved.relative_to(staging_root)  # raises ValueError on escape
    return resolved
