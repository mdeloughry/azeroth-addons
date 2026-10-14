# Changelog

## 0.1.9

- Check GitHub stable releases at startup and hourly while Decky is running; show a compact plugin-update notice and one notification per new version per session.
- Add plugin version, release notes, manual checks and an automatic-check toggle to Settings.
- Request the exact versioned ZIP through Decky's installer, with a required SHA-256 checksum and normal installation confirmation. No custom catalogue is needed.
- Reject prereleases, older versions, unexpected download URLs and packages without a checksum. Recheck the release and active addon/engine work before opening the installer.
- Add frontend updater regression tests to validation and release checks.

Install this build once through the existing Latest URL to receive future update notices. Updating reloads the plugin; finish addon operations first. Device verification of the Decky installation dialog/reload remains pending.

## 0.1.8

- Make installed-addon inventory read-only. Refreshing or searching does not run automatic adoption or replace unmanaged addon folders.
- Serialize reads and writes per installation; recheck paths, drive availability and running-game protection when queued operations begin.
- Stop the engine process group on timeout/cancellation before releasing an operation lock.
- Validate frontend, backend, tag versions and release notes before publishing a GitHub release. Include a SHA-256 checksum asset.
- Add GitHub installation, beta testing, contributor, security and release guides. Distribution is through GitHub; store submission is not planned.
- Correct third-party licence notices and include dependency licence texts in release packages.

Install through Decky Settings → Developer → Install Plugin from URL, using the ZIP attached to this release. Existing settings and credentials live outside the plugin directory.

This is an early preview. Fresh-device and community compatibility testing remains required; experimental rollback stays off by default.

## 0.1.7

- Simplify Quick Access Menu to one installed list, updates first, with update/remove icons and direct search/settings navigation.
- Disable Install for installed packages; normalize engine package slugs to match catalogue identities.
- Overlay activity on the addon being processed. Update All retains overall item counts.
- Exclude executable-only GitHub repositories from addon search; ignore expected Steam cancellation reports.

## 0.1.6

- Add source checkboxes and hide results from unconfigured download sources.
- Offer source setup/manual-install help on request.
- Disable instawow's terminal progress renderer for Decky subprocess operations.

## 0.1.5

- Show readable titles, compact icon actions, compatibility, dates and download counts.
- Clarify source statuses and preserve search relevance ordering.

## 0.1.4

- Use the structured addon catalogue instead of the interactive CLI search picker.
- Load host CA roots for verified provider and error-reporting HTTPS.

Older builds: [GitHub releases](https://github.com/mdeloughry/azeroth-addons/releases).
