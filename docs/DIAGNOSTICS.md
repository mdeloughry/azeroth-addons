# Diagnostics and privacy

Open the full manager → Diagnostics to inspect errors, expand details or clear the local journal. Report bugs with the error code, plugin/Decky/SteamOS versions and reproduction steps. Avoid posting raw logs or secrets.

## Local journal

The backend and frontend record structured errors locally. The journal is bounded to 200 entries, groups repeats, and lives in Decky's per-plugin settings directory. Redaction happens before storage. Credentials, credential-like strings, home paths and plugin paths are scrubbed; this is not a guarantee that every possible upstream string is harmless.

Normal Steam "User canceled" rejections are not treated as failures. Actual unhandled errors remain recorded.

## Optional reporting

Plugin update checks are separate from error reporting. Enabled by default from 0.1.9, they request public release metadata/checksums from GitHub, with the plugin version in the User-Agent. No provider token, device identifier, addon list or local path is included. GitHub receives normal network metadata such as your IP address. Disable automatic checks in Settings; manual checks and confirmed update downloads still contact GitHub. Background updater failures appear in Settings without repeatedly filling the error journal.

Remote reporting is off by default. Enable **Send error reports** in Settings or Diagnostics to send redacted events to the maintainer's GlitchTip instance. The first-error prompt is optional; dismissing it keeps reporting off. There is no analytics/device identifier added by the plugin.

Use **Preview what would be sent** before opting in. Payloads include error codes/messages/details, stack frames when available, plugin/engine/platform versions and operation context. Error messages and engine output can include **addon names, provider IDs and installation IDs**. These are not all stripped. Do not assume a report is anonymous simply because home paths and credentials are redacted. The destination server also receives normal connection metadata such as your IP address.

Your source credentials and custom reporting credential are not intentionally included in payloads. A custom DSN is stored privately, masked in the UI and never logged as a destination. Inspect the preview if the error contains private information.

## Your own destination

In Diagnostics choose Sentry-compatible reporting and save your project's DSN for GlitchTip, Bugsink or Sentry. Clearing a custom DSN returns to the built-in destination. Alternatively choose a plain JSON webhook. Use HTTPS; HTTP is allowed only for loopback destinations.

Sends are rate limited, failures do not fail addon operations, and failed sends are not retried in a loop. The test-report action can send a test before reporting is enabled because you explicitly requested that send.

## Connection failures

- `CERTIFICATE_VERIFY_FAILED`: the plugin uses verified HTTPS with host-maintained CA roots. Check the device clock and server certificate chain if failure persists; do not disable verification.
- Rate limit/authentication errors: check the source credential and wait for limits to reset. Never paste keys into issues.
- Missing/incompatible engine: first-start runtime download needs network; confirm Linux x86-64 and report the runtime status.

For sensitive vulnerabilities use [security reporting](../SECURITY.md), not the public bug form.
