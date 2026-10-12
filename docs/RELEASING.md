# GitHub release process

GitHub is the distribution channel. The ZIP asset keeps the name `azeroth-addons.zip`. There is no store submission/build path to maintain.

## Prepare

1. Update versions in `package.json` and `backend/azeroth_addons/__init__.py` together. Add this version's entry to `CHANGELOG.md`.
2. Update user docs for changed behavior and record actual hardware coverage/known limits. Prepare an honest release summary.
3. Run the checks below and inspect the generated archive. Never include credentials, local journals or personal screenshots.

```bash
.venv/bin/python -m pytest -q
pnpm run validate
python3 scripts/check-release.py
./scripts/package-release.sh
```

The backend tests use fixtures. CI also runs Python 3.11/3.13; builds/typechecks the UI; downloads the pinned engine with checksum verification; and checks Linux engine startup. These are not substitutes for the [device matrix](BETA_TESTING.md).

## Publish

Commit reviewed changes and create `v<version>` at that exact commit. Before every push, obtain explicit maintainer confirmation for the commit/tag being pushed. This is the project's working Git safety rule. Do not push automatically from a packaging script.

Tag pushes trigger Release. Its publication job validates tag/frontend/backend/changelog versions, runs backend tests and frontend validation, verifies the bundled runtime and builds the ZIP before publishing. Release notes come from the matching changelog section. A checksum asset is included.

Manual workflow dispatch requires an existing release tag and checks out that tag; it does not publish the current `main` branch under a guessed tag. Re-running publication can replace assets for an existing release, so verify that replacement is intended.

Versions with a suffix such as `0.2.0-beta.1` are marked GitHub prereleases and are not promoted to Latest by this workflow. Give testers that release's versioned asset URL. Ordinary versions are marked Latest. If users rely on a short redirect, point it at:

```text
https://github.com/mdeloughry/azeroth-addons/releases/latest/download/azeroth-addons.zip
```

## Verify after publication

Check the release/CI runs, public asset URL, checksum, and version inside the downloaded ZIP. For a regular release, follow the latest redirect and verify it serves that version. Keep evidence in the release or testing issue; avoid asserting a running device was upgraded merely because CI passed.

Publish a short summary of changes, upgrade steps, known limits and ways to report bugs/contribute. Recruit testers explicitly when ready; this document does not send invitations.

## Repository settings

Recommended settings are private vulnerability reporting and required validation before merging to `main`, with a maintainer release workflow. Enabling these changes repository behavior and must be checked/configured separately. Ensure direct-push expectations and branch protection agree before changing them.
