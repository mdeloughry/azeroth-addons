# Roadmap

## GitHub preview release

- [x] Stable release ZIP name and latest-download URL.
- [x] Read-only inventory and per-installation serialization.
- [x] Backend/frontend validation, version checks and release notes before publication.
- [x] Contributor/bug/PR/security documentation and issue forms.
- [ ] Independent fresh-install/upgrade and controller verification; record the [beta matrix](BETA_TESTING.md).
- [ ] Add sanitized screenshots from real SteamOS hardware to the user guide.
- [ ] Enable private security reporting and appropriate branch protection after confirming repository settings/workflow fit.
- [ ] Open and label small starter issues from the items below; invite the first testers.

Repository-hosting settings and tester invitations are separate from adding local documentation. Check them live rather than assuming a Markdown file enables a GitHub feature.

## Small contribution candidates

- Improve installation/troubleshooting copy from an actual fresh device run.
- Test long/translatable UI strings and keyboard/controller focus; provide concrete screenshots.
- Capture sanitized real-engine fixtures for list/update output, including unchanged and failed targets.
- Improve source-status and empty-state messages without exposing CLI internals.
- Add a Linux integration harness using disposable addon folders; verify unmanaged files remain byte-identical.

Each should become a scoped issue with acceptance criteria and a way to verify it. There are no existing "good first issue" tickets implied by this list.

## Before broader promotion

- Tighten update-target parsing against actual engine output: a source identifier alone does not prove an update is available.
- Verify process detection distinguishes same-flavour copies in separate Proton prefixes; avoid false blocks from shared Windows paths.
- Replace approximate managed-folder matching with exact engine-owned folder metadata.
- Improve cancellation/failure events for all operations and cross-view progress synchronization.
- Validate GitHub ZIP game compatibility before exposing Install where practical; the engine currently makes the final compatibility decision.
- Test ordinary SteamOS updates and document the actual minimum supported Decky/runtime versions.

## Later features

Reviewed adoption of manual addons (explicit preview/consent, locks and game-running gates), verified rollback UX, richer source metadata, and direct-identifier flows can be designed after the preview is reliable.

No Decky store submission is planned. GitHub distribution, reproducible builds and open contributions are the intended path.
