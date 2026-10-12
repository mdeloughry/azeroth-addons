# Azeroth Addons

A controller-first World of Warcraft addon manager for Decky Loader on SteamOS.
Manage local WoW installations from Gaming Mode: search, install, check updates,
update one/all, and remove managed addons.

**Early preview.** Independent hardware coverage is still being collected.
Testers, bug reports, documentation improvements and code contributions are
welcome. Distribution is through **GitHub releases**; no Decky store submission
is planned. This README describes the current source; use the bundled docs and
changelog for the release installed on your device.

## Install

Requires Decky Loader 3.x, SteamOS/Linux x86-64, a local WoW installation and
network access. The bundled instawow 7.2.1 engine downloads its embedded runtime
on first start. No separate pip/engine installation is required on the device.

1. Open Decky settings in Gaming Mode, enable Developer mode if needed, then
   open **Developer → Install Plugin from URL**.
2. Paste the URL below and install. Use the asset ZIP, not GitHub's source ZIP.
3. Open Azeroth Addons. Restart Decky/reboot if it does not appear.
4. Wait for engine preparation, then press **Find World of Warcraft**.

```text
https://github.com/mdeloughry/azeroth-addons/releases/latest/download/azeroth-addons.zip
```

Repeat this installation to upgrade. Settings/credentials live outside the
plugin directory; GitHub releases do not provide Decky store update notices.
Developer → Install Plugin from ZIP File and manual extraction are fallback
options. Full instructions, custom installations, removal and downgrade limits:
[Getting started](docs/GETTING_STARTED.md).

## Use it

- The slide-out panel shows one installed list, updates first. Update targets
  have an update icon; managed addons have remove. Update All sits above the
  list; other navigation/check/refresh controls are below.
- Search and cog icons open Find Addons and Settings directly. Choose the
  installation first; writes apply to that copy/version only.
- Search checks only selected, available sources. Unchecked sources are skipped;
  unconfigured download sources are greyed out and their results excluded.
  Open a source's **Set up** help for credential/manual-install instructions.
- Install disables for installed packages. An activity overlay identifies the
  current addon; byte-level download percentages are not available.
- The full manager shows manually installed/unmanaged folders. Inventory,
  refresh and search do not adopt or replace those files. Automatic adoption
  is disabled.

Close WoW before install/update/remove, and keep it closed until the operation
finishes. Reads/writes serialize per installation and recheck drive availability,
canonical addon paths and running-game protection when queued work starts.
Different installations can proceed independently. Experimental rollback stays
off by default and still needs hardware verification.

## Addon sources

| Source | Current behavior |
| --- | --- |
| GitHub | Keyless catalogue/direct search. Direct results need release ZIPs; the engine checks actual game compatibility. Optional token increases API limits. |
| TukUI | Keyless ElvUI/Tukui catalogue entries for supported game versions. |
| WoWInterface | Catalogue/engine support for Retail. |
| CurseForge | Downloads require your own approved API key. Without one, its source is disabled and results hidden. The experimental direct-API flag is separate. |
| Wago | No name-search entries or direct-identifier install UI. Use its website/manual installation; engine downloads for known identifiers require a token. |

Credentials stay on-device and are masked in the UI. Eligibility is not a
promise that every upstream request or archive succeeds. Source restrictions,
manual installation and flavour-specific results are covered in
[Getting started](docs/GETTING_STARTED.md#sources).

## Errors and privacy

Diagnostics shows a bounded local error journal. Remote reporting is **off by
default**; opt in to send redacted errors to the maintainer's GlitchTip, or
configure your own Sentry-compatible destination/webhook. Preview the payload
before enabling. Error text can include addon/provider/installation identifiers;
redaction does not make every report anonymous.

See [diagnostics/privacy](docs/DIAGNOSTICS.md). Use the
[bug form](https://github.com/mdeloughry/azeroth-addons/issues/new/choose) for
ordinary failures; [security reporting](SECURITY.md) explains sensitive reports.
Never post API keys or unredacted device logs.

## Test or contribute

- [Beta test guide and hardware matrix](docs/BETA_TESTING.md)
- [Contributing and local development](CONTRIBUTING.md)
- [Roadmap and small contribution candidates](docs/ROADMAP.md)
- [Community conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md) · [Release process](docs/RELEASING.md)

AI-assisted contributions are welcome. Contributors are responsible for
correctness, licence compatibility, clear changes and honest validation.

```bash
pnpm install --frozen-lockfile
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
pnpm run validate
python3 scripts/check-release.py
./scripts/package-release.sh
```

Unit tests use fixture installations; no WoW, provider keys or Linux engine
execution is required. The shipped backend is stdlib-only Python 3.11. CI also
checks Python 3.13. A UI build/fixture test does not verify real Steam controller
behavior; record on-device checks separately.

## Architecture

React UI (`src/`) → Decky RPC (`main.py`) → addon services → engine/providers.
`InstawowAdapter` owns CLI syntax. Installation discovery/persistence,
provider capabilities and redacted telemetry have separate backend modules.
The engine binary is pinned/checksum-verified at package time; it is not checked
into Git. Addon contents are treated as data, not executed by the plugin.

[Implementation history](docs/implementation-plan.md) records earlier design
choices; current behavior and limits are documented in the guides above.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE),
[third-party notices](THIRD_PARTY_LICENSES.md) and the dependency licence texts
shipped in release archives.
