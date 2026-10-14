# Contributing

Bug reports, device testing, documentation, accessibility work and code contributions are welcome. The project is an early preview, distributed through GitHub. There is no Decky store submission planned.

AI-assisted contributions are welcome. Contributors remain responsible for correctness, licence compatibility, readable changes and honest validation. Never commit credentials or private device data.

## Start here

- Read [README](README.md), [roadmap](docs/ROADMAP.md) and [beta test guide](docs/BETA_TESTING.md).
- Check existing [issues](https://github.com/mdeloughry/azeroth-addons/issues) before opening one. Use the bug/feature forms.
- Discuss larger changes in an issue before implementation. Small fixes can go straight to a pull request.
- Follow [conduct guidance](CODE_OF_CONDUCT.md). Sensitive vulnerabilities belong in [security reporting](SECURITY.md).

## Local setup

Use Node.js 20+, pnpm 9 and Python 3.11+. CI covers Python 3.11 (Decky's runtime contract) and 3.13. Python packages are development-only; the shipped backend must remain stdlib-only and valid Python 3.11.

```bash
pnpm install --frozen-lockfile
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
pnpm run validate
python3 scripts/check-release.py
```

Unit tests use fixture installations and a fake engine: no WoW installation, API keys or Linux engine binary required. Frontend builds use Steam components supplied by Decky; there is no standalone browser development server. Real controller behavior needs a SteamOS device.

`pnpm run validate` also runs Node's frontend updater tests. They transpile the actual updater module with mocked Decky/React/lifecycle boundaries; they do not prove an actual SteamOS install/reload. The updater's internal Decky transport is isolated in `src/pluginUpdater.ts` and must retain a manual-install fallback.

For a device package, run `./scripts/package-release.sh`, copy the resulting ZIP to your device, then install it through Decky's Developer ZIP installer. The bundled engine is Linux x86-64; it cannot execute on macOS. [Getting started](docs/GETTING_STARTED.md) covers device setup.

## Code boundaries

- Keep CLI syntax in `InstawowAdapter`; service/RPC/UI code uses provider-neutral models.
- `inventory` and list/search paths must not adopt, download, replace or delete addon files. Automatic adoption is disabled.
- Every service operation touching installation state uses its per-installation lock. Resolve availability, canonical paths and running-game protection after acquiring it. Do not call another locked method from inside that lock.
- Stop subprocesses before releasing locks on cancellation/timeout. Add regressions for failures and queued operations, not just happy paths.
- Keep provider credentials out of frontend payloads, logs, issues and tests. Use fictional credentials in tests.
- Use Steam's controller-aware controls, accessible action labels, and wrapping titles. Verify UI changes on-device when possible; identify stand-in/browser checks as such.

## Pull requests

Explain the user-visible problem, the fix and tests run. Include a regression for a bug when there is a meaningful seam. Keep changes focused; do not refactor unrelated code.

For UI changes attach a screenshot or recording, with viewport/device details. If you lack a SteamOS device, say so; a maintainer/tester can perform device verification. Do not claim tests you did not run. Document limitations and changed behavior together with code.

Maintainers handle versions, tags and publishing. See [release process](docs/RELEASING.md).
