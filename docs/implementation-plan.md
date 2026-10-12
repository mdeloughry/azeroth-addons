# Azeroth Addons — Decky Plugin Implementation Plan

## Summary (read this first)

**Build**: A Decky Loader plugin that manages WoW addons from Gaming Mode.

**Engine**: Bundled, pinned **instawow 7.2.1** binary. Zero user setup.

**Architecture**: Provider-neutral + engine-neutral. instawow is the default engine, not the architecture.

**Key facts from research** (all verified Oct 2026):

1. **Decky Loader v3.2.10**. Plugin template: `api_version: 1`, `@decky/api` + `@decky/ui`, Rollup, pnpm 9.
2. **Backend = plain `async def` methods** on `class Plugin`. No decorators. `_main`/`_unload`/`_uninstall` lifecycle.
3. **Plugins run as the `deck` user**. No `root` flag. Perfect for addon file management.
4. **Bundled binaries live in `bin/`** and must be `chmod 0o755` by the plugin at startup.
5. **instawow 7.2.1** ships an official standalone Linux x86-64 binary. We pin + checksum-verify it.
   - sha256 of `instawow-cli-7.2.1-x86_64-unknown-linux-gnu.zip`: `4f211cb1055a4b1b2348af1be4820701de727cfad5f8f2cc7d527536a268766c`
6. instawow is **GPL-3.0-or-later**. Redistribution is permitted with license text. Plugin will be GPL-3.0-or-later too.
7. instawow supports **WoW Forever** (`_classic_beta_`), Retail (`_retail_` → `mainline`), Classic Era (`_classic_era_` → `vanilla_classic`), plus Mists/TBC/Cata/Titan.
8. **instawow needs Python ≥3.13**. Decky backends run Python 3.11. So the plugin **cannot import instawow as a library**. Subprocess CLI is the only integration path — which matches the spec's `InstawowAdapter` design.
9. **Multi-profile built in**: `-p <profile>`, all state relocated via `INSTAWOW_HOME` env var.
10. **API-key reality**: instawow bundles no CurseForge key. Since **2026-07-16**, CurseForge CDN downloads require an API key. GitHub, TukUI, WoWInterface work keyless. So "zero-config" covers non-CurseForge sources; CurseForge gets an optional user-key entry. This is a spec deviation driven by upstream reality.
11. **CurseForge direct API**: application-gated, keys non-transferable, API-data caching forbidden. Direct `CurseForgeProvider` stays a separate, feature-flagged milestone — as the spec already demands.

---

## Decisions (made, with reasons)

1. **Repo**: new project at `/Volumes/Secondary/Projects/azeroth-addons`. Plugin dir name `azeroth-addons`.
2. **License**: **GPL-3.0-or-later** (we distribute a GPL binary inside; this removes all doubt). `THIRD_PARTY_LICENSES.md` carries instawow's `COPYING` + notes.
3. **Integration**: subprocess per operation. **Only `InstawowAdapter` knows CLI syntax.** Sequential per-addon calls for accurate progress and per-addon error attribution.
4. **State**: `INSTAWOW_HOME` → `DECKY_PLUGIN_RUNTIME_DIR/instawow`. One instawow profile per installation, written as config JSON directly (no interactive `configure`).
5. **Secrets**: stored in the plugin settings file. Injected as **env vars** on each instawow call (`INSTAWOW_ACCESS_TOKENS_CFCORE` etc.). Never logged. Never returned to the frontend (masked, e.g. `cf…f3a`).
6. **Python backend**: **stdlib only** (no pip deps — Decky can't install them). Compatible with Python 3.11.
7. **UI**: full-page route via `routerHook.addRoute` (controller-friendly browsing) + compact QAM panel (status, Update All, open-page button).
8. **Custom paths**: built-in `openFilePicker` from `@decky/api` + a quick-picks list (Steam libraries, `/run/media`, `/mnt`, `~/Games`, known compatdata roots). No custom browser in MVP — the picker is usable again as of Decky v3.2.10.
9. **Providers MVP**: registry + capability objects + health status. Real search/metadata comes from the engine. `CurseForgeProvider` = disabled-by-default skeleton (M14). `WagoProvider` = stub (instawow handles Wago; its API needs a Patreon-tier token).
10. **Update checks**: `instawow update --dry-run` output parsed by the adapter. **Installed list**: `instawow list -f json`. **Unmanaged detection**: diff AddOns folder listing vs managed set.
11. **Rollback**: `instawow rollback <addon>` is interactive. MVP pipes the version choice; if flaky on-device, the capability flag flips to `false` and the button hides. Spec allows "rollback where supported".
12. **Search dedupe**: none across providers in MVP. Only exact `provider:id` matches merge.

---

## Repo layout

```text
azeroth-addons/
├── plugin.json              # name "Azeroth Addons", api_version 1, NO root flag
├── main.py                  # Decky Plugin class = thin RPC surface only
├── decky.pyi
├── package.json             # @decky/api, @decky/ui, react-icons, tslib
├── rollup.config.js         # @decky/rollup preset
├── tsconfig.json
├── README.md                # install, usage, dev, hosting-style guide
├── LICENSE                  # GPL-3.0-or-later
├── THIRD_PARTY_LICENSES.md  # instawow GPL-3.0 text + provenance (URL, sha256)
├── py_modules/.keep
├── bin/.gitkeep             # instawow binary lands here at package time (gitignored)
├── backend/azeroth_addons/
│   ├── __init__.py
│   ├── errors.py            # AzerothAddonsError + code constants + envelope helpers
│   ├── logctx.py            # "installation=… engine=… provider=… operation=…" log helper + redaction
│   ├── security.py          # path canonicalisation, AddOns-target validation, symlink checks
│   ├── process_detection.py # per-installation WoW-running detection via /proc scan
│   ├── settings.py          # persistence: installations.json + app settings (SettingsManager)
│   ├── installations/
│   │   ├── models.py        # WowInstallation dataclass (spec's shape)
│   │   ├── flavours.py      # folder → flavour map, marker validation
│   │   ├── discovery.py     # Steam libs (libraryfolders.vdf), compatdata, /run/media, /mnt, ~/Games
│   │   └── manager.py       # registry CRUD, availability checks, duplicate detection
│   ├── engines/
│   │   ├── base.py          # AddonEngine ABC + EngineCapabilities
│   │   ├── registry.py
│   │   └── instawow.py      # InstawowEngine + InstawowAdapter (only place CLI is known)
│   ├── providers/
│   │   ├── base.py          # AddonProvider ABC + ProviderCapabilities
│   │   ├── models.py
│   │   ├── registry.py
│   │   ├── curseforge.py    # M14: feature-flagged skeleton, env credential only
│   │   ├── github.py        # minimal metadata provider (releases API), capability-gated
│   │   └── wago.py          # stub: unavailable, documented reason
│   └── addons/
│       ├── models.py        # Addon dataclass (spec's shape) + state machine
│       ├── search.py        # AddonSearchService: fan-out, per-provider failure isolation
│       └── service.py       # orchestration: gates, security checks, events, error mapping
├── src/                     # frontend (React/TS)
│   ├── index.tsx            # definePlugin: QAM panel + route registration
│   ├── api.ts               # typed callable wrappers, event listeners, error types
│   ├── state.tsx            # context: selected installation, caches, event sync
│   ├── components/          # AddonRow, StatusBadge, ProgressRow, ErrorNote
│   └── views/
│       ├── FullPage.tsx     # Tabs: Addons | Find Addons | Installations | Settings
│       ├── MainPanel.tsx    # QAM compact view
│       ├── InstallationSelector.tsx
│       ├── InstalledList.tsx
│       ├── SearchView.tsx
│       └── SettingsView.tsx # engine status, source status, optional keys (masked)
├── scripts/
│   ├── fetch-instawow.sh    # pinned download + sha256 verify + unzip + chmod
│   └── package-release.sh   # pnpm build → fetch binary → zip (store layout)
├── tests/
│   ├── fixtures/            # fake WoW roots, canned instawow outputs, stub binary
│   ├── test_discovery.py
│   ├── test_flavours.py
│   ├── test_installations.py
│   ├── test_engines.py
│   ├── test_providers.py
│   ├── test_search.py
│   ├── test_security.py
│   └── test_process_detection.py
└── .github/workflows/ci.yml # pnpm build + tsc + pytest
```

**RPC envelope**: every method returns `{"ok": true, "data": …}` or `{"ok": false, "error": {code, message, details?, installationId?, provider?, engine?}}`. Exceptions never cross the RPC boundary raw.

**Events** (`decky.emit`): `az:runtime_status`, `az:installations_changed`, `az:operation` (`{installationId, kind, current, total, addon?, phase}`).

---

## Behaviour notes that matter

1. **Multiple versions in one WoW root** → each version folder becomes its own `WowInstallation`. Multiple copies of the same flavour across drives are all kept.
2. **Discovery never hardcodes** one appid or prefix: parse `libraryfolders.vdf`, then scan **all** `compatdata/*/pfx/drive_c` for markers (`Wow.exe`, `.build.info`, `WTF`, `Data`, `Interface/AddOns`), plus `/run/media/*`, `/mnt/*`, `~/Games`.
3. **Missing drives are persisted**, flagged `available: false`, and auto-heal on rescan/heartbeat.
4. **WoW-running protection**: gate install/update/remove/rollback per installation. `/proc/*/cmdline` scan for the installation's canonical root. Retail running does not block Era.
5. **Security**: all destructive ops canonicalise paths first; target must be `<validated root>/Interface/AddOns`; symlink-resolved paths must stay inside the root; reject `/`, `/home`, etc. instawow does extraction (safe by construction); our `security.py` guards registration and operations, and is fully unit-tested.
6. **Instawow warmup**: PyApp binary materialises its venv on first run (needs network). `_main` does: chmod → `--version` verify → background warmup → emit runtime status (`verifying → warming → ready` / `incompatible` / `missing`).
7. **Logging**: every operation logs the context line. Token env vars are never logged; log redactor strips `x-api-key`, bearer tokens, `INSTAWOW_ACCESS_TOKENS_*`.

---

## Milestones (each ends with a commit)

1. **M1 — Decky skeleton**: template files adapted, echo RPC round-trip, QAM panel + route, CI green.
2. **M2 — Bundle instawow**: `fetch-instawow.sh` (pinned 7.2.1 + sha256), runtime bootstrap + `runtime_status`, package script.
3. **M3 — Abstractions**: engines/base+registry, providers/base+models+registry, capabilities, errors.
4. **M4 — Installation model + persistence** (CRUD RPC, installations.json).
5. **M5 — Discovery** (Steam libs, compatdata, flavours, multi-version roots, rescan).
6. **M6 — Custom path selection** (quick-picks + file picker + validation).
7. **M7 — Installation selector UI** (badges, availability, default selection).
8. **M8 — Profile mapping** (one instawow profile per installation, validated via `instawow debug`).
9. **M9 — Installed list + reconcile** (`list -f json` adapter, unmanaged detection, UI).
10. **M10 — Updates** (check via dry-run parse, update one/all with progress events, rollback capability-gated).
11. **M11 — Search** (engine search adapter + parser, AddonSearchService, provider-grouped results UI).
12. **M12 — Install/remove** (flows, confirmations, WoW-running gating).
13. **M13 — Hardening** (process detection integration, security pass, provider health, error/log polish).
14. **M14 — CurseForgeProvider prototype** (feature-flagged, developer credential via env only, terms-checked docs, no secrets in repo).

M14 scope guard: prototype stays **disabled in production builds** until CurseForge application is approved (their terms: keys non-transferable, no caching, CDN now key-enforced). Direct downloads ship only after approval.

---

## Testing

1. **Installations**: retail/era/forever discovery, multi-flavour roots, multiple retail copies, custom + external + missing + reconnected drives, Steam libs, Proton prefixes. All via fixture trees — **no real WoW needed**.
2. **Providers**: registry, capabilities, unavailable/auth-failed/rate-limited paths, normalisation, duplicate results.
3. **Engines**: registry, executable validation, version check, profile mapping, argument generation, output parsing (canned fixtures), unavailable engine.
4. **Safety**: path traversal, invalid AddOns targets, canonical paths, symlink escapes, WoW-running detection (injected process lists).
5. **Frontend**: `tsc` + `pnpm build` must pass; manual on-device checklist below.

---

## Verification

**Local (CI)**: `pytest` green, `pnpm build` green, `scripts/package-release.sh` produces a store-layout zip.

**On SteamOS** (numbered, run once hardware is available):

1. Copy zip to `/home/deck/homebrew/plugins/`, unzip, restart Decky.
2. Confirm plugin appears; open the page.
3. Check runtime status shows instawow `7.2.1 ready` (first warmup needs network).
4. Run a discovery; confirm at least one installation per attached drive/flavour.
5. Add a custom installation via the picker; confirm validation + duplicate rejection.
6. Install a keyless-source addon (e.g. `github:…` or TukUI ElvUI) end-to-end.
7. Update one, then Update All; watch progress events.
8. Remove an addon; confirm folder gone.
9. Launch WoW; confirm operations are blocked with the correct message; close WoW; confirm unblocked.
10. Skim the log file for context lines and absence of secrets.

**Known risk to verify first on device**: the binary's glibc floor (built on ubuntu-22.04, so ≥2.35; SteamOS 3 is Arch-based and newer — expected fine, confirmed only by running `bin/instawow --version`).

---

## Assumptions

1. Plugin store submission is a later, separate step (requires a public repo + Decky review) — repo visibility is the user's call at publish time.
2. "Forever" maps to instawow's `forever_classic` / `_classic_beta_` (confirmed supported since instawow 7.2.0).
3. No WTF sync, no manifest sync, no source-preference setting in MVP — the data model leaves room for all three.

---

# Implementation status (updated during the build)

**Status: MVP complete.** All fourteen milestones are implemented, with the
deviations recorded below.

## What shipped

1. **Decky skeleton** - `plugin.json` (`api_version: 1`, no `root` flag), thin
   `main.py` RPC surface, React frontend with a Quick Access Menu panel and a
   full-screen route.
2. **Bundled engine** - `scripts/fetch-instawow.sh` pins instawow 7.2.1,
   verifies the SHA-256 and installs `bin/instawow`; the plugin `chmod`s and
   verifies it at startup, warms it in the background and publishes
   `verifying → warming → ready` status events.
3. **Abstractions** - `AddonEngine` + `EngineRegistry` + `EngineCapabilities`;
   `AddonProvider` + `ProviderRegistry` + `ProviderCapabilities`; a shared
   structured error model and RPC envelope.
4. **Multi-installation model** - persisted registry, per-installation engine
   profile, availability recomputed on load, missing drives retained and healed.
5. **Discovery** - Steam `libraryfolders.vdf`, every Proton prefix, removable
   media, `~/Games`, plus bounded walks for custom layouts; one installation per
   game version.
6. **Custom paths** - quick-pick locations, the Decky folder picker, validation
   before registration, duplicate rejection.
7. **Installation selector** - controller-friendly dropdown with availability
   and running badges.
8. **Profiles** - one instawow profile per installation (`az-<installation-id>`),
   written as config JSON (no interactive `configure`), validated through
   `instawow debug` and surfaced in Settings.
9. **Listing and reconciliation** - `list --format json` with a tolerant parser
   (unparsed records are logged as a schema-drift warning), unmanaged folders
   detected and left strictly alone.
10. **Updates** - `update --dry-run` parsed into targets, per-addon updates with
    `n / m` progress events, Update All with per-addon failure isolation, and a
    bulk-update fallback when nothing can be enumerated.
11. **Search** - concurrent fan-out to the engine and every enabled provider,
    per-source failure isolation, exact-identity dedupe, installed-state
    annotation.
12. **Install and remove** - routed through the engine, gated per installation.
13. **Hardening** - per-installation `/proc` process detection, path and archive
    validation, independent provider health, redacted logs and error details.
14. **CurseForge prototype** - `CurseForgeProvider` behind the
    `enableDirectCurseForge` flag, credential from the plugin store or
    environment, `allowModDistribution` respected, no caching, no secrets in the
    repository.

## Deviations from the original plan

1. **GitHub and TukUI became real providers.** They are keyless, so real search
   works with zero configuration instead of waiting for the CurseForge
   milestone.
2. **`security.is_protected` checks both lexical and resolved paths.** `/etc` is
   a symlink to `/private/etc` on macOS and `/home` is an automount, so the
   canonical form alone was not enough.
3. **A version directory must carry markers.** An empty `_retail_` folder no
   longer registers as an installation.
4. **Rollback is capability-gated behind `enableExperimentalRollback`.** The
   engine's rollback is an interactive prompt; Azeroth Addons drives it by
   feeding the choice, but the capability reports `false` until a user opts in,
   so the UI never offers a button that cannot work.
5. **`update_all` counts only pre-existing addons that changed version**, so a
   newly appeared addon is not misreported as an update.
6. **Tests use pytest + pytest-asyncio** (`requirements-dev.txt`); the backend
   itself remains stdlib-only, enforced by `tests/test_compatibility.py`, which
   also parses every backend file under the Python 3.11 grammar Decky provides.

## Still to verify on hardware

1. The engine binary's glibc floor. It is built on `ubuntu-22.04` (glibc >= 2.35)
   and SteamOS 3 is newer, but this is only provable by running
   `bin/instawow --version` on the device.
2. The push-to-rescue behaviour of `instawow rollback` without a TTY, for the
   experimental rollback path.
3. Live provider responses (`list --format json`, `search`, `update --dry-run`)
   against the real engine, to confirm the tolerant parsers match upstream
   output. The parsers log a warning if the shape drifts.

### Search and HTTPS correction (12 October 2026)

The pinned engine's `search` command is an interactive install picker, not a
machine-readable search endpoint. Decky's subprocess has no terminal, so search
now reads the same public v8 structured catalogue directly, with exact engine
flavour filtering and an in-memory four-hour cache. Installs still use the
engine. GitHub remains an independent direct search provider. The public
catalogue contains WoWInterface and TukUI projects but currently no Wago entries.

Source and reporting HTTPS clients now share a verified SSL context which also
loads host-maintained CA bundles. This addresses embedded Python builds whose
OpenSSL default paths point at a build-machine prefix. Certificate and hostname
verification remain enabled. Device verification is still required.

### Source selection and install correction (v0.1.6)

Controller-friendly source checkboxes select both engine catalogue results and
direct searches. Credential-gated sources are disabled, excluded from results,
and rejected at the install RPC before invoking the engine. Setup/manual-install
guidance is shown only when the user opens help for that source. Catalogue source
filters run before result ranking and limits.

GlitchTip issues 5 and 6 recorded the same `prompt_toolkit` progress renderer
failure (`PermissionError` followed by `EOFError`) for CurseForge and GitHub
installs on v0.1.5. All engine calls now pass global `--verbose`: the pinned
instawow 7.2.1 implementation disables terminal progress rendering when verbosity
is positive. Device installation retries remain required to verify the fix.

### Installed-state and item progress correction (v0.1.7)

The engine's package list contains numeric IDs plus canonical slugs. Slugs now
drive UI identities, matching catalogue search results. Successful installs mark
their search row installed immediately, and removal clears that state. Install
events identify the pending addon from the start; Update All identifies each
target before its engine call. Item overlays show activity without inventing
byte-level percentages.

GlitchTip issue 8 showed an executable-only GitHub updater being offered as an
addon. Direct GitHub search now checks release ZIP availability, with bounded
concurrency and a short cache. The engine still validates actual archive and game
compatibility. Expected Steam `User canceled` rejections no longer generate
frontend error reports; other unhandled rejections remain reported.

The Quick Access Menu now shows one compact installed list, with update targets
first and update/remove icons per row. Update All sits above it; check, refresh,
installation management and diagnostics sit below. Search and settings icons
open dedicated full-page routes with the matching initial tab. The panel no
longer duplicates update rows or displays healthy engine/version badges.

---

## Error tracking (added after the MVP)

Two layers, privacy-first.

1. **Local journal, always on** - `telemetry/privacy.py`, `telemetry/journal.py`.
   Redacted at ingestion, bounded to 200 events, repeats folded into a count,
   persisted at `<settings>/error-journal.json`. Nothing leaves the device.
2. **Opt-in remote reporting** - `telemetry/reporter.py`, `telemetry/sentry.py`.
   Implements the Sentry **Store API** directly, with no SDK, so the backend
   stays stdlib-only and reports still land in a proven tool (GlitchTip,
   Bugsink or Sentry). Off by default, with the exact request previewable,
   HTTPS required (loopback may use HTTP), rate limited, and failures surfaced
   in the UI instead of retried in a loop. A built-in destination means opting
   in needs no configuration.

Decisions taken:

1. **A destination, not a vendor.** The SDK-based options are excluded twice
   over: the backend cannot install packages, and implementing the protocol once
   keeps the destination a leaf that can be swapped. The default is the author's
   own GlitchTip project, so opting in takes one switch; an advanced user can
   override it with their own DSN or webhook.
2. **Consent, not silence.** Sending errors to the author makes the author the
   recipient of other people's telemetry, so reporting stays off by default and
   is offered - once - after an error happens, with a toggle in Settings and
   Diagnostics. The exact payload is previewable before opting in.
3. **The DSN is a credential** when the user supplies one: stored with the other
   credentials (mode 0600), never returned to the frontend, and shown only in a
   keyless form (`https://host/project`). The built-in DSN ships in code as a
   public client key (as Sentry intends), is used only when the user has set
   none, and is likewise never returned to the UI. Rotating it needs a release.
4. **Two redaction bugs were found by the new tests**: `Authorization: Bearer
   <token>` was redacting the scheme word and leaving the token, and a bare
   `token` key was not treated as sensitive. Both are fixed, with tests.
5. **Engine-backed sources are no longer labelled "unavailable"** (see below).
