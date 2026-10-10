# Third-party licences

Azeroth Addons itself is licensed **GPL-3.0-or-later** (see `LICENSE`).

This file records the third-party components that are **bundled** with, or
**linked against**, the plugin, and the provenance of the bundled binary.

---

## 1. instawow (bundled addon engine)

| Field | Value |
| --- | --- |
| Project | instawow |
| Upstream | https://github.com/layday/instawow |
| Version | **7.2.1** (released 2026-09-20) |
| Licence | **GPL-3.0-or-later** |
| Artifact | `instawow-cli-7.2.1-x86_64-unknown-linux-gnu.zip` |
| Download | https://github.com/layday/instawow/releases/download/v7.2.1/instawow-cli-7.2.1-x86_64-unknown-linux-gnu.zip |
| SHA-256 | `4f211cb1055a4b1b2348af1be4820701de727cfad5f8f2cc7d527536a268766c` |

**How it is bundled**

1. `scripts/fetch-instawow.sh` downloads exactly the artifact above.
2. The SHA-256 is verified and a mismatch is fatal.
3. The unmodified binary is installed as `bin/instawow` and marked executable.
4. The upstream licence text is fetched to `third_party/instawow/COPYING` and
   ships inside the release archive.

The pinned version, artifact name and checksum are also recorded in code
(`backend/azeroth_addons/__init__.py`) and surfaced in the Settings screen.

**Why the licence permits this**

instawow is GPL-3.0-or-later, which permits redistribution of the unmodified
binary together with its licence text and an offer of corresponding source.
Azeroth Addons executes instawow as a **separate program** over its documented
command-line interface (never by linking or importing it - instawow requires
Python >= 3.13 while Decky's plugin backend runs Python 3.11). The two programs
communicate at arm's length, which is why Azeroth Addons can carry the same
GPL-3.0-or-later licence without ambiguity.

Source for the bundled version is available at the upstream tag
`v7.2.1`, and on PyPI as `instawow==7.2.1`.

---

## 2. Decky Loader APIs

| Component | Licence | Use |
| --- | --- | --- |
| `@decky/api` | MIT | frontend RPC, events, file picker |
| `@decky/ui` | MIT | Steam Deck UI components |
| `@decky/rollup` | MIT | build preset |
| Decky Loader itself | GPL-3.0 | host application (not bundled) |

---

## 3. Frontend npm packages

| Package | Licence | Use |
| --- | --- | --- |
| `react` / `react-dom` | MIT | provided by the Steam client at runtime |
| `react-icons` | MIT | plugin icon |
| `tslib` | 0BSD | TypeScript helpers |
| `rollup`, `typescript` | MIT / Apache-2.0 | build-time only |

---

## 4. Addon sources and content

Azeroth Addons downloads addon archives from third-party catalogues at the
user's request. Those addons are the property of their authors and are not
redistributed by Azeroth Addons.

1. Addon archives are always treated as untrusted data and are never executed.
2. Provider terms are respected, including author opt-outs from third-party
   distribution.
3. Direct provider APIs are only used where the provider's terms allow it - see
   the CurseForge section of `docs/implementation-plan.md`.
