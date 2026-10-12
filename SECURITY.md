# Security reporting

The latest published GitHub build is the supported baseline for investigation. This is an early preview, not a completed security audit. Older releases may contain known defects; upgrade before reproducing a problem when safe.

For vulnerabilities involving path escapes, unsafe addon writes, credentials or reporting privacy, use GitHub's private vulnerability reporting interface if the repository offers it. Otherwise open an issue titled **Private security contact requested**, without exploit details, and ask the maintainer for a confidential channel. Private reporting availability is a repository setting; this document does not imply it is enabled.

Include the plugin version, platform, impact and a minimal reproduction once a private channel is established. Use fixture folders and fictional credentials. Do not publish real tokens, DSNs, usernames, paths or addon archives containing someone else's data.

Ordinary bugs belong in the [issue forms](https://github.com/mdeloughry/azeroth-addons/issues/new/choose). Confirmed fixes will be recorded in the changelog; coordinated disclosure can be discussed privately. No response-time guarantee is made.
