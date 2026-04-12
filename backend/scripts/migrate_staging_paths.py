"""Migrate staged_attachments.staged_path from absolute to relative.

Idempotent: already-relative paths are skipped.
Usage: uv run python scripts/migrate_staging_paths.py
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ccas.db"

KNOWN_PREFIXES = (
    "/data/staging/",
    "/Users/",
)


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "SELECT id, staged_path FROM staged_attachments WHERE staged_path IS NOT NULL"
    )
    rows = cur.fetchall()

    updated = 0
    skipped = 0

    for row_id, staged_path in rows:
        p = Path(staged_path)
        if not p.is_absolute():
            skipped += 1
            continue

        for prefix in KNOWN_PREFIXES:
            if staged_path.startswith(prefix):
                parts = staged_path.split("/staging/", 1)
                if len(parts) == 2:
                    relative = parts[1]
                    cur.execute(
                        "UPDATE staged_attachments SET staged_path = ? WHERE id = ?",
                        (relative, row_id),
                    )
                    updated += 1
                    break
        else:
            print(f"WARN: unknown prefix, skipped id={row_id} path={staged_path}")

    conn.commit()
    conn.close()
    print(f"Done: updated={updated} skipped={skipped}")


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    if not db.exists():
        print(f"DB not found: {db}")
        sys.exit(1)
    migrate(db)
