"""Regression checks for the repository-owned Codex skill projection."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_codex_skills_has_no_tracked_symlinks() -> None:
    """DHPK owns runtime projection; CCAS must not track stale symlink aliases."""
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", ".codex/skills"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    tracked_symlinks = []
    for line in result.stdout.splitlines():
        mode, path = line.split("\t", maxsplit=1)
        # A deleted path remains in the index until the change is staged. It is
        # already absent from the checkout and should not fail this guard.
        if mode.split(maxsplit=1)[0] == "120000" and (REPO_ROOT / path).is_symlink():
            tracked_symlinks.append(path)
    assert not tracked_symlinks, (
        "Do not commit cross-repository .codex/skills symlinks; use the DHPK installer"
    )
