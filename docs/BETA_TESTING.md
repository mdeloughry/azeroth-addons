# Beta testing

The goal is a small group of independent testers before wider promotion. Use GitHub release assets, collect reproducible reports, and keep experimental rollback off. Store submission is not part of this plan.

## Start safely

1. Read [getting started](GETTING_STARTED.md), source limitations and [privacy](DIAGNOSTICS.md).
2. Back up the selected game's `Interface/AddOns` and `WTF` folders. Use a disposable installation or a small addon for your first test.
3. Record plugin version, Decky version, SteamOS version/channel, device and game flavour.
4. Close WoW before writes. Opening/refreshing the list while it runs is a read-only test; install/update/remove should be refused.

## Record evidence

Check off only what you tested. Include pass/fail, device/version details and the associated issue for a failure. These checks are a test plan, not claims of completed hardware coverage.

| Test | Result / evidence |
| --- | --- |
| Fresh install through URL; plugin visible and controller usable | Pending |
| First-start runtime download, including slow/offline failure recovery | Pending |
| Upgrade from previous release; credentials/installation settings preserved | Pending |
| GitHub plugin check/notification; notes, opt-out, offline recovery, manual check | Pending |
| Plugin update confirmation/cancel/retry; exact ZIP checksum, reload and settings preserved | Pending |
| Retail, Classic Era, Forever and Classic discovery | Pending |
| Internal drive, SD/external drive, missing/reconnected drive | Pending |
| Multiple copies of the same flavour across Proton prefixes | Pending; running detection may be conservative |
| Search checked sources only; unchecked/credential-gated sources absent | Pending |
| GitHub/TukUI/Retail WoWInterface install, list, update and remove | Pending |
| CurseForge setup and download with tester's own approved key | Optional; never share credentials |
| Installed button disabled; activity overlay identifies the current item | Pending |
| Read/refresh leaves manually installed folder contents unchanged | Pending |
| Writes blocked while matching game runs; another flavour remains usable | Pending |
| Concurrent requests serialize for one installation; independent copies remain usable | Pending |
| Cancellation/network failure stops progress and permits later operations | Pending |
| Local diagnostics and reporting preview; opt-in/out honored | Pending |
| Small viewport, controller focus, long names and supported SteamOS channels | Pending |

## Reporting

Use the [bug form](https://github.com/mdeloughry/azeroth-addons/issues/new/choose). Include expected/actual behavior, exact steps and redacted Diagnostics details. For UI problems, attach a device screenshot/recording without private desktop content. Enable reporting only if you are comfortable with its payload; it is not required for testing.

Maintainers should invite roughly 5–10 testers, then track device/flavour coverage in a beta issue. Do not call a build broadly validated from one developer's device, fixture tests, or screenshots rendered with substitute Steam controls.

Promote a wider release after safety regressions pass, clean install/upgrade succeeds on independent devices, and blockers in the matrix are resolved. Keep a versioned ZIP for rollback and the known limitations visible in release notes.
