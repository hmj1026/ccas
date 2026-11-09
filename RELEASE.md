# Release

CCAS releases are a `develop` → `master` merge commit plus an annotated `vX.Y.Z`
tag. CI owns the tag, the images and the GitHub Release; the human owns the
version choice, the upgrade notes and the merge.

## Configuration

| Token | Value |
|---|---|
| `{BASE_BRANCH}` | `develop` |
| `{RELEASE_BRANCH}` | `master` |
| `{TAG_PREFIX}` | `v` |
| `{VERSION_FILES}` | every path in `PINS` of [`scripts/release_tag.py`](scripts/release_tag.py) (rewritten by `scripts/bump_version.py`) |
| `{CHANGELOG}` | [`docs/upgrade-guide.md`](docs/upgrade-guide.md) — newest-first `## vX.Y.Z（Minor\|Patch）— YYYY-MM-DD — <summary>` sections. GitHub Release notes are generated, not hand-written. |
| `{VALIDATE_CMD}` | the pre-push hook ([`scripts/pre-push.sh`](scripts/pre-push.sh)), which runs on the release commit push |
| `{RELEASE_WORKFLOW}` | [`.github/workflows/release-tag.yaml`](.github/workflows/release-tag.yaml) → dispatches [`release-docker.yaml`](.github/workflows/release-docker.yaml) on the tag |

Versioning is SemVer: a schema migration or user-visible behaviour change is
at least Minor; tooling-only changes are Patch.

## Steps

1. On an up-to-date `develop` with a clean worktree, run
   `python3 scripts/bump_version.py X.Y.Z`. It rewrites every pin and refreshes
   the backend editable install (the package version is dynamic, so a stale
   install fails `test_version_metadata`).
2. Write the `vX.Y.Z` section at the top of the upgrade-guide release list, and
   update its migration sentence (the `v… 無資料庫 schema 變更` / `含資料庫 schema 變更`
   line under the non-Docker upgrade steps). List the PRs since the previous tag
   (`git log --oneline vPREV..develop --no-merges`).
3. Commit only the bump and upgrade-guide changes, push `develop`, and open the
   PR `develop` → `master` titled exactly `Release vX.Y.Z`. The push runs the
   full pre-push suite; that run is the release validation. With the
   release-creator skill this is the runner's `prepare` phase, given the files
   `bump_version.py` printed plus `docs/upgrade-guide.md`.
4. A human merges with **Create a merge commit**.
5. CI does the rest: `release-tag.yaml` re-verifies every pin against the
   title, tags the merge commit, and dispatches `release-docker.yaml`, which
   builds multi-arch images and creates the Release with `docker-compose.yml`
   and `example.env` attached. Never create the tag or the Release by hand, and
   skip the release-creator `publish` phase: an existing tag fails
   `release-tag.yaml`.
6. Watch both runs (`gh run list --workflow release-tag.yaml`, then the
   `workflow_dispatch` run of `release-docker.yaml`), then confirm the images
   with `python3 scripts/check_release_images.py vX.Y.Z`.

`master` ends one merge commit ahead of `develop` after every release; the trees
are identical, so no back-merge or force-sync is needed.
