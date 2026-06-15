"""Atomic file write helpers shared across storage-touching modules.

The crash-safety contract is temp-then-rename: write the full new contents to
a sibling temp file on the *same directory/filesystem*, then ``os.replace`` it
over the destination. ``os.replace`` is atomic on POSIX when source and target
share a mount point, so a concurrent reader (or a crash) sees either the prior
file or the complete new file, never a partial write.

Callers that need a "produce the bytes into a temp path, then swap" flow where
a third-party library (e.g. pikepdf) owns the actual write can use
``atomic_replace_via`` to get a managed temp path + cleanup without duplicating
the finally/unlink boilerplate.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Write *data* to *path* atomically via temp-then-rename.

    The temp file is created in ``path``'s parent directory so the final
    ``os.replace`` stays on a single filesystem and is therefore atomic on
    POSIX. On any failure the temp file is removed; the destination is left
    untouched. Exceptions propagate -- callers must not swallow them.

    Args:
        path: Destination path to overwrite.
        data: Full new file contents.
        mode: Optional permission bits to apply to the temp file before the
            rename (e.g. ``0o600`` for secrets).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def atomic_replace_via(
    path: Path,
    producer: Callable[[Path], None],
    *,
    suffix: str = ".tmp",
) -> None:
    """Atomically replace *path* with output produced by *producer*.

    ``producer`` is handed a temp path (a sibling of *path* on the same
    filesystem) and must write the complete new contents there. On success the
    temp file is ``os.replace``-d over *path*. Any leftover temp file is removed
    in a ``finally`` block, including when ``producer`` or the rename raises --
    the exception then propagates unchanged so the caller can fail the job.

    This is the right helper when a third-party library owns the actual write
    (e.g. ``pikepdf.Pdf.save(tmp_path)``); use ``atomic_write_bytes`` when the
    caller already holds the bytes in memory.

    Args:
        path: Destination path to overwrite.
        producer: Callback that writes the full new contents to the given temp
            path.
        suffix: Temp file suffix (kept on the same dir for atomic rename).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=suffix,
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        producer(tmp_path)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
