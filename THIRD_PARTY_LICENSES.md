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

**Source and build provenance**

The unmodified instawow binary is distributed under GPL-3.0-or-later, with
its licence text and source/build provenance recorded here.
Azeroth Addons executes instawow as a **separate program** over its documented
command-line interface (never by linking or importing it - instawow requires
Python >= 3.13 while Decky's plugin backend runs Python 3.11). The two programs
communicate through subprocess arguments and output.

Source and build configuration for the bundled version:
[upstream v7.2.1](https://github.com/layday/instawow/tree/v7.2.1),
[source archive](https://github.com/layday/instawow/archive/refs/tags/v7.2.1.tar.gz).
The package is also available on PyPI as `instawow==7.2.1`.

---

## 2. Decky Loader APIs

| Component | Licence | Use |
| --- | --- | --- |
| `@decky/api` | LGPL-2.1 | frontend RPC, events, file picker |
| `@decky/ui` | LGPL-2.1 | Steam Deck UI components |
| `@decky/rollup` | BSD-3-Clause | build preset (build-time only) |
| Decky Loader itself | GPL-3.0 | host application (not bundled) |

---

## 3. Frontend npm packages

| Package | Licence | Use |
| --- | --- | --- |
| `react` / `react-dom` | MIT | provided by the Steam client at runtime |
| `react-icons` | MIT for library code | icons; individual icon-set licences also apply |
| `tslib` | 0BSD | TypeScript helpers |
| `rollup`, `typescript` | MIT / Apache-2.0 | build-time only |

Font Awesome 5 icons (`react-icons/fa`) are by Font Awesome and licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Source: [Font Awesome](https://fontawesome.com/). They are used as UI glyphs;
display size/colour are styled by the plugin. The react-icons licence file
contains the library copyright notice and icon-set attributions.

Release archives include `third_party/licenses/` with the actual installed
Decky API/UI, react-icons and tslib licence texts. The runtime engine's COPYING
ships separately under `third_party/instawow/`.

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
