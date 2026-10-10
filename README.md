# Azeroth Addons

**A controller-first World of Warcraft addon manager for SteamOS Gaming Mode.**

Install one Decky plugin and manage every local World of Warcraft installation
from Gaming Mode. No Desktop Mode, no terminal, no `pip`, no `instawow`, no
config files.

---

## Summary (the short version)

1. **Install** the plugin into Decky Loader. Nothing else to set up.
2. **Scan** for WoW installations (Steam libraries, Proton prefixes, SD cards,
   external drives).
3. **Manage** addons per installation: list, reconcile, update one, update all,
   search, install, remove, roll back.

The bundled **instawow 7.2.1** engine does the heavy lifting. Azeroth Addons is
not built *around* instawow: engines and addon sources are pluggable layers, and
the UI only ever sees a provider-neutral addon model.

---

## What you need

| Requirement | Notes |
| --- | --- |
| Decky Loader | v3.x. The plugin uses `api_version: 1` (the current API). |
| SteamOS / Linux x86-64 | The bundled engine is an official upstream Linux x86-64 build. |
| A World of Warcraft installation | Retail, Classic Era, Forever, Classic, or a custom path. |

---

## Install

Every release publishes one asset with a **stable name**, so the download link
never changes between versions:

```text
https://github.com/mdeloughry/azeroth-addons/releases/latest/download/azeroth-addons.zip
```

### Option A - manual (works today)

1. Download `azeroth-addons.zip` from the link above (or the releases page).
2. Copy it to the handheld.
3. Unzip it into `/home/deck/homebrew/plugins/` so you get
   `/home/deck/homebrew/plugins/azeroth-addons/`.
4. Restart Decky Loader (or reboot).

### Upgrading / reinstalling

1. Re-download the same link; it always serves the newest release.
2. Unzip it over the existing folder - there is no need to remove it first.
3. Your **settings, credentials and error journal are kept**: they live in
   Decky's per-plugin settings directory, not inside the plugin folder.

### Option B - Decky plugin store

Store submission is a later, separate step: it requires a public repository and
passes through Decky's review. One item is still open:

1. **The engine binary** - `bin/instawow` is deliberately not committed (it is
   a 25 MB third-party download). The store build therefore needs either the
   `package.json` `remote_binary` mechanism (name, URL and the pinned SHA-256
   from `scripts/fetch-instawow.sh`) so Decky fetches and verifies it at install
   time, or a CI step that runs `scripts/fetch-instawow.sh` before packaging.

*Artwork: done. `assets/logo.png` (512×512) is rendered from `assets/logo.svg`
and referenced by `plugin.json`'s `publish.image`.*

---

## First run

1. Open the Quick Access Menu and select **Azeroth Addons**.
2. The plugin starts the bundled engine. **The first start downloads the
   engine's embedded Python runtime**, so it needs network access once and can
   take a little while. The status badge shows `verifying → warming → ready`.
3. Tap **Find World of Warcraft**. Discovery scans:
   - every Steam library listed in `steamapps/libraryfolders.vdf`;
   - every Proton prefix (`steamapps/compatdata/*/pfx/drive_c`);
   - `/run/media/*/*` and `/mnt/*` (SD cards and external drives);
   - `~/Games` (Lutris-style prefixes).
4. Every game version found becomes its own installation, for example
   *Retail - Internal*, *Classic Era - Internal*, *Forever - External (SDCARD)*.

---

## Using it

**Managing addons**

1. Pick the installation in the **World of Warcraft** dropdown.
2. The header shows installed count and available updates.
3. **Check for updates** resolves the newest versions.
4. **Update All** updates the selected installation only, with a `2 / 5`
   progress line.
5. Each addon row has its own **Update**, **Rollback** and **Remove** actions.

**Finding something new**

1. Open **Find Addons**.
2. Type a name and press **Search**.
3. Results are grouped by source (CurseForge, GitHub, Wago, TukUI, ...).
4. Press **Install**. Installs always run through the addon engine, never from
   the UI.

**Adding an installation**

1. Open **Installations** → **Add installation**.
2. Choose a starting location, or **Browse** for the folder.
3. The path is validated before registration. Pointing at a *World of Warcraft*
   root that contains several versions registers **each version separately**.

**Safety rules the plugin enforces**

1. Addon operations are blocked while that installation is running. Retail
   running does **not** block Classic Era.
2. Unmanaged addons are never modified or deleted.
3. Only `<WoW>/Interface/AddOns` is ever written to, after canonicalising the
   path and refusing symlink escapes and protected locations.

---

## Addon sources and API keys (important)

Azeroth Addons works out of the box, with one honest caveat.

| Source | Works with no setup? | Why |
| --- | --- | --- |
| GitHub | **Yes** | Public releases API. An optional token raises the rate limit. |
| TukUI | **Yes** | `api.tukui.org/v1` is public. |
| WoWInterface | **Yes** (Retail only) | Reached through the engine; no catalogue API exists. |
| Wago | Needs a Wago token | Wago requires a bearer token for addon downloads. |
| CurseForge | Needs a CurseForge API key | CurseForge has required an API key for downloads since **16 July 2026**, and instawow ships no shared key. |

**Add your own credentials in Settings** (optional, per source). They are stored
on the device only, injected into the engine as environment variables, never
logged, and never sent to the UI - the Settings screen shows only a masked hint.

There is also a **direct CurseForge API** provider built in. It ships
**disabled**, needs an approved credential, and is documented in
`docs/implementation-plan.md`. Nothing about normal operation depends on it.

---

## Security

1. Downloaded addons are treated as untrusted data. Nothing inside an addon is
   ever executed.
2. Paths are canonicalised before any destructive operation, and the target
   must be `<installation>/Interface/AddOns`.
3. Protected locations (`/`, `/home`, `/etc`, ...) are refused; symlink escapes
   are refused.
4. Archive handling enforces no absolute paths, no `../` traversal, no symlink
   escape, and size/member limits.
5. Credentials never reach the log or the frontend. Error details are redacted.
6. The plugin runs as the `deck` user, not as root.

---

## Error tracking and diagnostics

**Two layers, and the private one is the default.**

1. **Local journal - always on, never leaves the device.** Every error the
   backend or the UI produces is recorded on the device.
2. **Remote reporting - off until you turn it on.** Point it at a destination
   you control.

### The local journal

1. Records every structured error with its code, message, context
   (`installation`, `engine`, `provider`, `operation`) and stack frames.
2. **Redacts at ingestion**, so sensitive text never even reaches the file:
   credentials are stripped, usernames are removed from paths, and paths inside
   the plugin are rewritten relative.
3. Is bounded (200 events), folds repeats together with a `×N` count, and lives
   at `<plugin settings dir>/error-journal.json`.

Open **Azeroth Addons → Diagnostics** to read it, expand an event, or clear it.

### Remote reporting (opt-in)

Reports are sent using the **Sentry protocol** (the Store API), so they land in
[GlitchTip](https://glitchtip.com), Bugsink or Sentry with no extra tooling -
and **no SDK**, because the backend is stdlib-only.

1. Deploy **GlitchTip** (self-hosted, MIT, Sentry-compatible) using its official
   Docker Compose install.
2. Create a project in GlitchTip and copy its **DSN**.
3. In Azeroth Addons, open **Diagnostics → Send error reports**.
4. Paste the **DSN**, press **Save destination**, then **Send a test report**.
5. Turn **Send error reports** on. Errors appear in GlitchTip from then on.

Prefer a webhook? Switch the destination type to **Plain JSON webhook** and the
documented event JSON is POSTed to your URL instead.

### What is sent, and what is not

**Sent:** plugin version, Python/platform, engine name and version, the error
code and message, redacted details, stack frames, and the context tags.

**Never sent:** API keys, tokens, the DSN, your username, your home directory,
absolute plugin paths, addon names, or any device identifier.

Before enabling, press **Preview what would be sent** to see the exact request
body. The destination must be HTTPS (plain HTTP only for loopback), sends are
rate limited, and a failure is reported in the UI rather than retried in a loop.



---

## Architecture

```text
Steam Gaming Mode
        │
        ▼
Azeroth Addons (React / TypeScript)      src/
        │  envelopes + events only
        ▼
Decky Python backend                     main.py
        │
        ▼
Addon service layer                      backend/azeroth_addons/addons/
        │
        ├───────────────┬─────────────────────────┐
        ▼               ▼                         ▼
Engines            Providers                Installations
        │               │                         │
        │        ├── CurseForge (flagged)   discovery, flavours,
        │        ├── GitHub                 registry, availability
        │        ├── TukUI
        │        ├── Wago (engine-backed)
        │        └── WoWInterface (engine-backed)
        │
   instawow 7.2.1 (bundled binary)
        │
        ▼
<WoW>/Interface/AddOns
```

**Boundaries that are enforced by tests**

1. `InstawowAdapter` is the only class that knows instawow's CLI syntax.
2. The frontend contains no CLI flags, no subprocess calls and no provider URLs.
3. The backend is **stdlib-only** (Decky cannot install Python packages into a
   plugin) and is valid **Python 3.11** (what Decky runs).
4. Capabilities are discovered, not assumed: no code branches on
   `provider == "curseforge"`.

See `docs/implementation-plan.md` for the full design, the milestone plan and
the CurseForge compliance notes.

---

## Development

```bash
# Frontend
pnpm install
pnpm run typecheck      # tsc --noEmit
pnpm run build          # rollup -> dist/index.js

# Backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q

# Bundled engine (pinned + checksum-verified)
./scripts/fetch-instawow.sh
bin/instawow --version

# Distributable zip
./scripts/package-release.sh
```

Deploy to a device while developing:

```bash
rsync -av --delete ./ deck@steamdeck:/home/deck/homebrew/plugins/azeroth-addons/
```

### Repository layout

```text
azeroth-addons/
├── main.py                    Decky entry point: RPC surface only
├── plugin.json                Decky manifest (api_version 1, no root flag)
├── src/                       React frontend
│   ├── api.ts                 typed RPC + event subscription
│   ├── state.tsx              one hook owns all backend interaction
│   ├── components/            rows, badges, progress
│   └── views/                 QAM panel + full page (incl. Diagnostics)
├── backend/azeroth_addons/
│   ├── installations/         models, flavours, discovery, registry
│   ├── telemetry/             error journal, redaction, Sentry reporter
│   ├── engines/               base, registry, instawow adapter + engine
│   ├── providers/             base, registry, http, concrete providers
│   ├── addons/                models, service, search aggregator
│   ├── errors.py              structured error codes + RPC envelope
│   ├── security.py            path validation and archive guards
│   ├── process_detection.py   per-installation "game is running"
│   └── context.py             wires everything together
├── scripts/                   fetch-instawow.sh, package-release.sh
├── tests/                     226 tests, no WoW install required
└── assets/logo.svg            plugin artwork
```

---

## On-device verification checklist

Run this once on hardware after installing:

1. Plugin appears in the Quick Access Menu; the full page opens.
2. Runtime status reaches `instawow 7.2.1 ready` (first start needs network).
3. **Find World of Warcraft** finds at least one installation per attached drive.
4. Add a custom installation and confirm validation rejects a non-WoW folder.
5. Install an addon from a keyless source (for example `github:owner/repo`).
6. Update one addon, then **Update All**; watch the progress line.
7. Remove an addon; confirm its folder is gone.
8. Launch WoW and confirm operations are blocked with the right message; close
   the game and confirm they unblock.
9. Skim the log for `installation=... engine=... provider=... operation=...`
   lines and confirm no credential values appear.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Badge stuck on `warming` | First-run runtime download | Wait on network; or open Settings → **Start the engine** |
| `INSTAWOW_INCOMPATIBLE` | Engine cannot run on this system | Report it; the engine binary is an official upstream build |
| `WOW_RUNNING` | The game is open | Close that game version |
| `INSTALLATION_UNAVAILABLE` | SD card / drive not mounted | Reconnect and rescan; the installation is never deleted |
| A source is `degraded` | Upstream problem or rate limit | Other sources keep working; add a credential to raise limits |
| `ENGINE_UNSUPPORTED` on Rollback | Rollback is interactive in the engine | Enable **Experimental rollback** in Settings |
| Something failed and you are unsure why | The journal has the answer | **Diagnostics** tab → expand the event |

---

## License

**GPL-3.0-or-later** - see `LICENSE`, and `THIRD_PARTY_LICENSES.md` for the
bundled engine and its provenance.
