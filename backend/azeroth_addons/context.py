"""Application context.

One object owns the object graph (settings, installations, engines, providers,
services) so that ``main.py`` stays a thin RPC surface and every part of the
backend is constructible in a test without Decky.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import (
    BUNDLED_INSTAWOW_ARTIFACT,
    BUNDLED_INSTAWOW_SHA256,
    BUNDLED_INSTAWOW_URL,
    BUNDLED_INSTAWOW_VERSION,
    __version__,
)
from . import events
from .addons.search import AddonSearchService
from .addons.service import AddonService
from .engines import factory as engine_factory
from .engines.base import EngineStatus
from .engines.registry import EngineRegistry
from .errors import NOT_READY, AzerothAddonsError
from .installations.discovery import default_environment, quick_pick_locations
from .installations.manager import InstallationManager
from .logctx import get_logger, mask_secret
from .providers import factory as provider_factory
from .providers.registry import ProviderRegistry
from .settings import (
    CREDENTIAL_KEYS,
    SETTABLE_KEYS,
    InstallationStore,
    JsonStore,
    SettingsStore,
)

logger = get_logger()

Emitter = Callable[[str, Any], Awaitable[None]]


@dataclass
class PluginEnvironment:
    """Resolved paths for the running plugin."""

    plugin_dir: str
    settings_dir: str
    runtime_dir: str
    log_dir: str
    home_dir: str
    user: str = "deck"
    proc_root: str = "/proc"
    # Advanced escape hatch: point at a different engine build (dev/testing).
    instawow_binary: str | None = None

    @property
    def binary_path(self) -> str:
        return self.instawow_binary or os.path.join(self.plugin_dir, "bin", "instawow")

    @property
    def instawow_home(self) -> str:
        return os.path.join(self.runtime_dir, "instawow")

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> "PluginEnvironment":
        env = dict(env if env is not None else os.environ)
        home = env.get("DECKY_USER_HOME") or env.get("HOME") or os.path.expanduser("~")
        plugin_dir = env.get("DECKY_PLUGIN_DIR") or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        fallback_root = os.path.join(home, ".local", "share", "azeroth-addons")
        settings_dir = env.get("DECKY_PLUGIN_SETTINGS_DIR") or os.path.join(fallback_root, "settings")
        runtime_dir = env.get("DECKY_PLUGIN_RUNTIME_DIR") or os.path.join(fallback_root, "runtime")
        log_dir = env.get("DECKY_PLUGIN_LOG_DIR") or os.path.join(fallback_root, "logs")
        user = env.get("DECKY_USER") or env.get("USER") or "deck"
        return cls(
            instawow_binary=env.get("AZEROTH_INSTAWOW_BINARY") or None,
            plugin_dir=plugin_dir,
            settings_dir=settings_dir,
            runtime_dir=runtime_dir,
            log_dir=log_dir,
            home_dir=home,
            user=user,
        )


class AzerothAddonsContext:
    def __init__(self, env: PluginEnvironment, emit: Emitter | None = None) -> None:
        self.env = env
        self._emit_callback = emit
        self._initialized = False

        self.store = JsonStore(env.settings_dir)
        self.settings = SettingsStore(self.store)
        self.installations = InstallationManager(InstallationStore(self.store), self.settings)
        self.providers = ProviderRegistry()
        self.engines = EngineRegistry()

        self.service: AddonService
        self.search: AddonSearchService
        self._prepare_task: asyncio.Task | None = None

    # --- lifecycle ---------------------------------------------------------

    def initialize(self) -> "AzerothAddonsContext":
        if self._initialized:
            return self
        self.settings.load()
        self._ensure_runtime_dirs()

        provider_factory.build_registry(self.settings, self.providers)
        engine_factory.build_registry(
            self.engines,
            binary_path=self.env.binary_path,
            home_dir=self.env.instawow_home,
            settings=self.settings,
            status_callback=self._on_engine_status,
        )
        self.service = AddonService(
            self.installations,
            self.engines,
            self.providers,
            self.settings,
            emit=self.emit,
            proc_root=self.env.proc_root,
        )
        self.search = AddonSearchService(
            self.installations,
            self.engines,
            self.providers,
            self.service.installed_addons,
        )
        self._initialized = True
        logger.info(
            "context initialised plugin=%s engine=%s installations=%d",
            __version__,
            self.engines.default_id,
            len(self.installations.all()),
        )
        return self

    def _ensure_runtime_dirs(self) -> None:
        for directory in (self.env.settings_dir, self.env.runtime_dir, self.env.log_dir):
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # pragma: no cover - environment problem
                logger.warning("could not create %s: %s", directory, exc)

    def require_initialized(self) -> None:
        if not self._initialized:
            raise AzerothAddonsError(
                NOT_READY,
                "Azeroth Addons is still starting up. Try again in a moment.",
            )

    # --- events ------------------------------------------------------------

    async def emit(self, event: str, payload: Any = None) -> None:
        if self._emit_callback is None:
            return
        try:
            await self._emit_callback(event, payload)
        except Exception as exc:  # noqa: BLE001 - events must never break operations
            logger.debug("emit %s failed: %s", event, exc)

    async def _on_engine_status(self, status: EngineStatus) -> None:
        await self.emit(events.RUNTIME_STATUS, self.runtime_status(status))

    async def announce_runtime_status(self) -> None:
        await self.emit(events.RUNTIME_STATUS, self.runtime_status())

    # --- engine warm-up ----------------------------------------------------

    def start_engine_prepare(self) -> asyncio.Task:
        """Warm the engine in the background so the UI is never blocked."""
        if self._prepare_task is None or self._prepare_task.done():
            self._prepare_task = asyncio.create_task(self._prepare_engine_bg())
        return self._prepare_task

    async def _prepare_engine_bg(self) -> None:
        try:
            await self.service.prepare_engine()
        except Exception as exc:  # noqa: BLE001 - reported through status
            logger.warning("engine preparation failed: %s", exc)

    async def prepare_engine(self) -> dict[str, Any]:
        self.require_initialized()
        status = await self.service.prepare_engine()
        return status.to_dict()

    def cancel_tasks(self) -> None:
        task = self._prepare_task
        if task is not None and not task.done():
            task.cancel()

    # --- status ------------------------------------------------------------

    def runtime_status(self, engine_status: EngineStatus | None = None) -> dict[str, Any]:
        engine_payload = engine_status.to_dict() if engine_status else None
        return {
            "pluginVersion": __version__,
            "engine": engine_payload,
            "installations": self.installations.summary() if self._initialized else {},
            "binary": self.binary_info(),
            "paths": {
                "pluginDir": self.env.plugin_dir,
                "settingsDir": self.env.settings_dir,
                "runtimeDir": self.env.runtime_dir,
                "logDir": self.env.log_dir,
            },
        }

    def binary_info(self) -> dict[str, Any]:
        path = Path(self.env.binary_path)
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        return {
            "path": str(path),
            "exists": exists,
            "executable": bool(exists and os.access(path, os.X_OK)),
            "size": size,
            "bundledVersion": BUNDLED_INSTAWOW_VERSION,
            "artifact": BUNDLED_INSTAWOW_ARTIFACT,
            "downloadUrl": BUNDLED_INSTAWOW_URL,
            "sha256": BUNDLED_INSTAWOW_SHA256,
        }

    # --- settings ----------------------------------------------------------

    def settings_payload(self) -> dict[str, Any]:
        credentials = {}
        for key in CREDENTIAL_KEYS:
            value = self.settings.credential(key)
            credentials[key] = {
                "configured": bool(value),
                "hint": mask_secret(value) if value else "",
            }
        return {
            "values": {
                key: self.settings.get(key)
                for key in sorted(SETTABLE_KEYS)
            },
            "credentials": credentials,
            "selectedInstallationId": self.settings.get("selectedInstallationId"),
        }

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        self.settings.update(values)
        return self.settings_payload()

    def set_credential(self, key: str, value: str | None) -> dict[str, Any]:
        self.settings.set_credential(key, value)
        return self.settings_payload()

    # --- discovery helpers -------------------------------------------------

    def installation_options(self) -> list[dict[str, str]]:
        return quick_pick_locations(default_environment())

    def preview_path(self, path: str) -> dict[str, Any]:
        """Validate and describe a candidate path without registering it."""
        from .installations.discovery import discover_path
        from .security import validate_installation_root

        root = validate_installation_root(path)
        found = discover_path(root)
        return {
            "path": str(root),
            "found": [
                {
                    "rootPath": item.root_path,
                    "flavour": item.flavour,
                    "flavourLabel": item.label,
                    "locationLabel": item.location_label,
                }
                for item in found
            ],
        }
