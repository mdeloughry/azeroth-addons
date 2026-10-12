"""Shared test fixtures.

Tests never require a real World of Warcraft installation, a real Steam
library, or the real instawow binary: everything is built from fixtures
(including a scriptable fake engine binary).
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from azeroth_addons.addons.models import Addon, unmanaged_addon  # noqa: E402
from azeroth_addons.engines.base import (  # noqa: E402
    AddonEngine,
    EngineCapabilities,
    EngineStatus,
    ReconcileResult,
)
from azeroth_addons.installations.discovery import DiscoveryEnvironment  # noqa: E402
from azeroth_addons.installations.models import WowInstallation  # noqa: E402

VERSION_FOLDERS = ("_retail_", "_classic_era_", "_classic_beta_")


def make_version_dir(parent: Path, name: str, *, with_addons: bool = True) -> Path:
    version = parent / name
    version.mkdir(parents=True, exist_ok=True)
    (version / "WTF").mkdir(exist_ok=True)
    (version / "Data").mkdir(exist_ok=True)
    (version / ".build.info").write_text("## Build\n", encoding="utf-8")
    if with_addons:
        (version / "Interface" / "AddOns").mkdir(parents=True, exist_ok=True)
    return version


def make_wow_root(parent: Path, folders: Sequence[str] = VERSION_FOLDERS, name: str = "World of Warcraft") -> Path:
    root = parent / name
    root.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        make_version_dir(root, folder)
    return root


@pytest.fixture
def wow_root(tmp_path: Path) -> Path:
    """A WoW root containing Retail, Classic Era and Forever."""
    return make_wow_root(tmp_path)


@pytest.fixture
def installation(wow_root: Path) -> WowInstallation:
    return WowInstallation.create(
        root_path=str(wow_root / "_retail_"),
        flavour="retail",
        display_name="Retail - Internal",
        version_folder="_retail_",
        instawow_flavour="mainline",
        product_code="wow",
    )


@pytest.fixture
def make_installation(tmp_path: Path):
    def _make(folder: str = "_retail_", *, flavour: str = "retail", instawow_flavour: str | None = "mainline", parent: Path | None = None, root_name: str = "World of Warcraft") -> WowInstallation:
        base = parent or (tmp_path / root_name)
        version = make_version_dir(base, folder)
        return WowInstallation.create(
            root_path=str(version),
            flavour=flavour,
            display_name=f"{flavour} - Test",
            version_folder=folder,
            instawow_flavour=instawow_flavour,
        )

    return _make


@pytest.fixture
def fake_proc(tmp_path: Path):
    """Build a fake /proc tree with synthetic process command lines."""

    proc = tmp_path / "proc"
    proc.mkdir(exist_ok=True)

    def _add(pid: int, cmdline: str, *, cwd: str | None = None, exe: str | None = None) -> None:
        pid_dir = proc / str(pid)
        pid_dir.mkdir(exist_ok=True)
        (pid_dir / "cmdline").write_bytes(cmdline.replace("{NUL}", "\x00").encode("utf-8"))
        if cwd:
            os.symlink(cwd, pid_dir / "cwd")
        if exe:
            os.symlink(exe, pid_dir / "exe")

    _add.__doc__ = "Add a synthetic process entry."  # type: ignore[attr-defined]
    return proc, _add


@pytest.fixture
def discovery_env(tmp_path: Path, wow_root: Path) -> DiscoveryEnvironment:
    return DiscoveryEnvironment(home=tmp_path, scan_roots=(wow_root.parent,), extra_roots=())


# ---------------------------------------------------------------------------
# fake engine binary
# ---------------------------------------------------------------------------

FAKE_BINARY = '''#!/usr/bin/env python3
"""Scriptable stand-in for the bundled instawow binary."""
import json
import os
import sys

spec_path = os.environ.get("FAKE_INSTAWOW_SPEC")
spec = {}
if spec_path and os.path.exists(spec_path):
    with open(spec_path) as handle:
        spec = json.load(handle)

args = sys.argv[1:]
log_path = os.environ.get("FAKE_INSTAWOW_LOG")
if log_path:
    with open(log_path, "a") as handle:
        handle.write(json.dumps({"args": args, "env_home": os.environ.get("INSTAWOW_HOME")}) + "\\n")

while args:
    if args[0] in ("--profile", "-p"):
        args = args[2:]
    elif args[0] in ("--verbose", "-v"):
        args = args[1:]
    else:
        break

key = " ".join(args)
entry = spec.get(key)
if entry is None:
    entry = spec.get("default", {"code": 0, "stdout": "", "stderr": ""})

sys.stdout.write(entry.get("stdout", ""))
sys.stderr.write(entry.get("stderr", ""))
sys.exit(int(entry.get("code", 0)))
'''


@pytest.fixture
def fake_instawow(tmp_path: Path):
    """Returns (binary_path, spec_dict, log_path)."""
    binary = tmp_path / "bin" / "instawow"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(FAKE_BINARY, encoding="utf-8")
    os.chmod(binary, binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    spec: dict[str, Any] = {}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    os.environ["FAKE_INSTAWOW_SPEC"] = str(spec_path)
    log_path = tmp_path / "calls.jsonl"
    os.environ["FAKE_INSTAWOW_LOG"] = str(log_path)
    yield binary, spec, log_path
    os.environ.pop("FAKE_INSTAWOW_SPEC", None)
    os.environ.pop("FAKE_INSTAWOW_LOG", None)


@pytest.fixture
def write_spec(fake_instawow):
    _binary, spec, _log = fake_instawow
    spec_path = Path(os.environ["FAKE_INSTAWOW_SPEC"])

    def _write(**entries: dict[str, Any]) -> dict[str, Any]:
        spec.clear()
        spec.update(entries)
        spec_path.write_text(json.dumps(spec))
        return spec

    return _write


@pytest.fixture
def read_calls(fake_instawow):
    _binary, _spec, log_path = fake_instawow

    def _read() -> list[dict[str, Any]]:
        if not log_path.exists():
            return []
        return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]

    return _read


@pytest.fixture
def make_adapter(fake_instawow, tmp_path: Path):
    from azeroth_addons.engines.instawow import InstawowAdapter

    binary, _spec, _log = fake_instawow

    def _make(*, tokens: dict[str, str] | None = None, home: Path | None = None) -> InstawowAdapter:
        return InstawowAdapter(
            binary,
            home or (tmp_path / "instawow-home"),
            token_provider=lambda: tokens or {},
        )

    return _make


# ---------------------------------------------------------------------------
# fake engine implementation (for service/search tests)
# ---------------------------------------------------------------------------


class FakeEngine(AddonEngine):
    engine_id = "fake"
    display_name = "Fake Engine"

    def __init__(
        self,
        *,
        available: bool = True,
        addons: Sequence[Addon] | None = None,
        unmanaged: Sequence[Addon] | None = None,
        updates: Sequence[Addon] | None = None,
        search_results: Sequence[Addon] | None = None,
        capabilities: EngineCapabilities | None = None,
        fail_update_ids: Sequence[str] = (),
        search_error: Exception | None = None,
    ) -> None:
        self.available = available
        self.addons = list(addons or [])
        self.unmanaged = list(unmanaged or [])
        self.updates = list(updates or [])
        self.search_results = list(search_results or [])
        self._capabilities = capabilities or EngineCapabilities(
            install=True,
            update=True,
            remove=True,
            reconcile=True,
            rollback=True,
            search=True,
            list_installed=True,
        )
        self.fail_update_ids = set(fail_update_ids)
        self.search_error = search_error
        self.calls: list[tuple[Any, ...]] = []

    def capabilities(self) -> EngineCapabilities:
        return self._capabilities

    async def status(self) -> EngineStatus:
        return EngineStatus(
            engine_id=self.engine_id,
            display_name=self.display_name,
            state="ready" if self.available else "error",
            available=self.available,
            version="9.9.9",
            capabilities=self.capabilities(),
        )

    async def prepare(self) -> EngineStatus:
        return await self.status()

    async def list_installed(self, installation: WowInstallation) -> list[Addon]:
        self.calls.append(("list_installed", installation.id))
        return list(self.addons)

    async def reconcile(self, installation: WowInstallation) -> ReconcileResult:
        self.calls.append(("reconcile", installation.id))
        return ReconcileResult(managed=list(self.addons), unmanaged=list(self.unmanaged))

    async def check_updates(self, installation: WowInstallation) -> list[Addon]:
        self.calls.append(("check_updates", installation.id))
        return list(self.updates)

    async def install(self, installation, provider, provider_id, *, replace: bool = False) -> Addon:
        self.calls.append(("install", installation.id, provider, provider_id, replace))
        addon = Addon(
            id=f"{provider}:{provider_id}",
            name=provider_id,
            provider=provider,
            provider_id=provider_id,
            installed_version="1.0.0",
        )
        self.addons.append(addon)
        return addon

    async def update(self, installation, addon: Addon) -> Addon:
        self.calls.append(("update", installation.id, addon.id))
        if addon.id in self.fail_update_ids:
            from azeroth_addons.errors import UPDATE_FAILED, AzerothAddonsError

            raise AzerothAddonsError(UPDATE_FAILED, f"failed {addon.id}", installation_id=installation.id)
        addon.installed_version = "2.0.0"
        addon.state = "current"
        return addon

    async def update_all(self, installation) -> list[Addon]:
        self.calls.append(("update_all", installation.id))
        return list(self.updates)

    async def remove(self, installation, addon: Addon) -> None:
        self.calls.append(("remove", installation.id, addon.id))

    async def rollback(self, installation, addon: Addon) -> Addon:
        self.calls.append(("rollback", installation.id, addon.id))
        addon.installed_version = "0.9.0"
        return addon

    async def search(self, installation, query: str, *, limit: int = 25) -> list[Addon]:
        self.calls.append(("search", installation.id, query, limit))
        if self.search_error is not None:
            raise self.search_error
        return list(self.search_results)


class RecordingEmitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    async def __call__(self, event: str, payload: Any = None) -> None:
        self.events.append((event, payload))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def payloads(self, event: str) -> list[Any]:
        return [payload for name, payload in self.events if name == event]


@pytest.fixture
def emitter() -> RecordingEmitter:
    return RecordingEmitter()


@pytest.fixture
def addon_factory():
    def _make(provider: str = "curseforge", provider_id: str = "masque", *, version: str = "1.0.0", name: str | None = None, folder: str | None = None, state: str = "current") -> Addon:
        return Addon(
            id=f"{provider}:{provider_id}",
            name=name or provider_id,
            provider=provider,
            provider_id=provider_id,
            installed_version=version,
            folder_name=folder,
            state=state,
        )

    return _make


@pytest.fixture
def unmanaged_factory():
    return unmanaged_addon


@pytest.fixture
def seed_installation():
    """Register a fixture installation in a manager and return the stored copy."""
    from azeroth_addons.installations.discovery import Discovered

    def _seed(installations, installation):
        installations.register_discovered(
            Discovered(
                root_path=installation.root_path,
                flavour=installation.flavour,
                label="Retail",
                version_folder=installation.version_folder,
                instawow_flavour=installation.instawow_flavour,
                product_code=None,
            )
        )
        return installations.get(installation.id)

    return _seed


@pytest.fixture
def stack(tmp_path: Path):
    """Build a wired-up service/search stack around a fake engine."""
    from types import SimpleNamespace

    from azeroth_addons.addons.search import AddonSearchService
    from azeroth_addons.addons.service import AddonService
    from azeroth_addons.engines.registry import EngineRegistry
    from azeroth_addons.installations.manager import InstallationManager
    from azeroth_addons.providers.registry import ProviderRegistry
    from azeroth_addons.settings import InstallationStore, JsonStore, SettingsStore

    def _build(
        *,
        engine: AddonEngine | None = None,
        providers: Sequence[object] = (),
        proc_root: str = "/proc",
        emitter: object | None = None,
        register=None,
    ) -> SimpleNamespace:
        store = JsonStore(tmp_path / "settings")
        settings = SettingsStore(store)
        settings.load()
        installations = InstallationManager(InstallationStore(store), settings)
        if register is not None:
            register(installations)

        engines = EngineRegistry()
        chosen = engine or FakeEngine()
        engines.register(chosen, default=True)

        provider_registry = ProviderRegistry()
        for provider in providers:
            provider_registry.register(provider)

        service = AddonService(
            installations,
            engines,
            provider_registry,
            settings,
            emit=emitter,
            proc_root=proc_root,
        )
        search = AddonSearchService(
            installations,
            engines,
            provider_registry,
            service.installed_addons,
        )
        return SimpleNamespace(
            settings=settings,
            installations=installations,
            engines=engines,
            engine=chosen,
            providers=provider_registry,
            service=service,
            search=search,
        )

    return _build
