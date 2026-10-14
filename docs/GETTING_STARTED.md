# Install and use Azeroth Addons

## Requirements

- SteamOS/Linux x86-64, Decky Loader 3.x and a local WoW installation.
- Network access for providers and first-start engine runtime download.
- Retail, Classic Era, Forever or Classic version folders with real WoW markers. Multiple installations and removable drives are supported, subject to the [beta test matrix](BETA_TESTING.md).

Distribution is through [GitHub releases](https://github.com/mdeloughry/azeroth-addons/releases). No store submission is planned. This is an early preview; independent hardware coverage is still being collected.

## Install from Gaming Mode

1. Open Decky in the Quick Access Menu and open its settings cog.
2. Enable Developer mode if needed, then open **Developer**.
3. Under **Install Plugin from URL**, paste the link below and press Install. Labels can vary slightly between Decky versions.
4. Follow Decky's confirmation, then open **Azeroth Addons**. If it does not appear, restart Decky or reboot.

```text
https://github.com/mdeloughry/azeroth-addons/releases/latest/download/azeroth-addons.zip
```

Use the release asset named `azeroth-addons.zip`, not GitHub's generated source-code ZIP. You can instead download that asset and use Developer → Install Plugin from ZIP File.

[Decky's Developer installer implementation](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/frontend/src/components/settings/pages/developer/index.tsx) is the upstream reference for these controls.

For a manual fallback, extract the plugin folder into `/home/deck/homebrew/plugins/azeroth-addons/` and restart Decky. Folder ownership/permissions must allow Decky to load it; the ZIP installer is preferred because it manages installation. Do not move or delete Decky's separate settings/runtime directories.

## First run

1. Wait for engine preparation. First start downloads its embedded runtime and requires network access.
2. Press **Find World of Warcraft**. Discovery scans Steam libraries/Proton prefixes, removable media, `/mnt` and `~/Games`.
3. Use **Manage installations** to add a custom folder or choose another discovered copy. Each game-version folder becomes its own installation.
4. Use the search icon to open **Find Addons**. Check available sources, search, then use the Install icon. Unavailable sources are disabled; open their setup help to see why.

## Daily use

The slide-out panel shows installed managed addons, updates first. Each update target has an update icon; managed rows have remove. Update All sits above the list. Check for updates, refresh, full manager, installations and diagnostics are below. The cog opens Settings.

The full manager also shows unmanaged addon folders. Reads and refreshes do not adopt or replace them. Automatic adoption is disabled. Addon writes wait for the per-installation lock and check drive availability, canonical paths and whether that game is running before starting.

Install is disabled for installed packages. The active addon gets an activity overlay; this is not a byte percentage. Update All provides overall item counts. Close WoW before changing addons and avoid launching it until the operation finishes.

## Sources

| Source | Search/install behavior |
| --- | --- |
| GitHub | Keyless catalogue/direct search. Direct results need release ZIPs; the engine checks actual archive/game compatibility. Optional token raises API limits. |
| TukUI | Keyless ElvUI/Tukui catalogue entries for supported game versions. |
| WoWInterface | Catalogue and engine support for Retail. |
| CurseForge | Downloads need an approved API key in Settings → credentials. Without it, results are excluded and the checkbox is disabled. The optional direct API flag is separate from engine credentials. |
| Wago | No name-search entries in the public catalogue. Use the website/manual installation; engine downloads for known identifiers require a token, but the UI has no direct-identifier install flow. |

Source eligibility means supported/configured, not that every upstream request or file will succeed. Check Diagnostics for failures. Some addons, including Spoken, are listed only for particular Classic/Forever variants; Retail search will not show them.

## Manual addon installation

Open the source website, download a ZIP for your game version, close WoW, and extract the actual addon folders into that version's `Interface/AddOns`. Refresh the plugin. These remain unmanaged: use the source site to update them and remove them manually. Do not delete `WTF` if you want to preserve in-game settings.

## Upgrade or remove the plugin

From 0.1.9, automatic plugin-update checks use GitHub stable releases at startup and hourly while Decky runs. A notification and slide-out notice appear for a newer version; Settings shows its release notes and an **Update plugin** button. This is separate from updating WoW addons.

Finish addon operations first, choose Update plugin, and confirm in Decky's installer. Opening the dialog does not mean installation has succeeded. Decky downloads the exact versioned ZIP, verifies the required SHA-256 checksum and reloads the plugin. If you cancel, the button becomes available to retry after 30 seconds. Settings, credentials and journal are stored separately.

Settings → **Automatically check for plugin updates** disables future background GitHub checks. Manual **Check for plugin updates** works while automatic checks are off. Each new version gets at most one notification per loaded frontend session. Failed checks retry after at least 15 minutes; addon management remains usable. Only stable releases newer than the installed version with the official ZIP and a valid checksum are offered. No GitHub token is sent by this updater.

The installer bridge uses Decky's internal `utilities/install_plugin` transport, as used by its own frontend; it is not a public `@decky/api` export. Loader changes can affect it. Hardware confirmation/cancellation/reload checks remain pending in the beta matrix. The fallback is to repeat the URL or ZIP installation and restart Decky if needed. Builds before 0.1.9 need that manual upgrade once to gain this updater. Users can keep their existing Decky catalogue.

Uninstall the plugin through Decky's settings. Removing the plugin does not remove WoW addons. To change versions, install a specific release asset; keep current settings backed up because downgrades are not guaranteed to understand newer settings schemas.

See [diagnostics/privacy](DIAGNOSTICS.md), [beta testing](BETA_TESTING.md) and [changelog](../CHANGELOG.md).
