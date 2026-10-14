"""Application context.

One object owns the object graph (settings, installations, engines, providers,
services) so that ``main.py`` stays a thin RPC surface and every part of the
backend is constructible in a test without Decky.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

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
from .errors import NOT_READY, AzerothAddonsError, set_error_sink
from .installations.discovery import default_environment, quick_pick_locations
from .installations.manager import InstallationManager
from .logctx import get_logger, mask_secret
from .providers import factory as provider_factory
from .providers.registry import ProviderRegistry
from .plugin_updates import PluginUpdates
from .settings import (
    CREDENTIAL_KEYS,
    SETTABLE_KEYS,
    InstallationStore,
    JsonStore,
    SettingsStore,
)
from .telemetry import privacy
from .telemetry.journal import ErrorEvent, ErrorJournal
from .telemetry.reporter import ErrorReporter

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


# The opt-in prompt fires after an error, at most this often, until answered.
NUDGE_THROTTLE_SECONDS = 60


class AzerothAddonsContext:
    def __init__(self, env: PluginEnvironment, emit: Emitter | None = None) -> None:
        self.env = env
        self._emit_callback = emit
        self._initialized = False

        self.store = JsonStore(env.settings_dir)
        self.settings = SettingsStore(self.store)
        self.plugin_updates = PluginUpdates(self.settings)
        self.installations = InstallationManager(InstallationStore(self.store), self.settings)
        self.providers = ProviderRegistry()
        self.engines = EngineRegistry()

        self.service: AddonService
        self.search: AddonSearchService
        self.journal: ErrorJournal
        self.reporter: ErrorReporter
        self._prepare_task: asyncio.Task | None = None
        self._report_tasks: set[asyncio.Task] = set()
        self._last_engine_status: EngineStatus | None = None
        self._last_nudge_at: float | None = None

    # --- lifecycle ---------------------------------------------------------

    def initialize(self) -> "AzerothAddonsContext":
        if self._initialized:
            return self
        self.settings.load()
        self._ensure_runtime_dirs()

        # Paths inside the plugin are reported relative, so nothing leaks where
        # the plugin happens to live.
        privacy.configure(plugin_root=self.env.plugin_dir)

        self.reporter = ErrorReporter(self.settings, runtime_provider=self.runtime_info)
        self.journal = ErrorJournal(self.store, on_event=self._on_error_event)
        set_error_sink(self._record_error)

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
        self._last_engine_status = status
        await self.emit(events.RUNTIME_STATUS, self.runtime_status(status))

    async def announce_runtime_status(self) -> None:
        await self.emit(events.RUNTIME_STATUS, self.runtime_status())

    # --- plugin updates ----------------------------------------------------

    async def plugin_update_plan(self, expected_version: str) -> dict[str, Any]:
        await self.plugin_updates.check(force=True)
        if self.service.operations_active() or (self._prepare_task is not None and not self._prepare_task.done()):
            raise AzerothAddonsError(NOT_READY, "Wait for addon operations and engine preparation to finish before updating the plugin.")
        return self.plugin_updates.install_plan(expected_version)

    # --- diagnostics -------------------------------------------------------

    def _record_error(self, fields: Mapping[str, Any]) -> None:
        """Sink for :mod:`errors`; called synchronously from the RPC guard."""
        context = dict(fields.get("context") or {})
        self.journal.record(
            ErrorEvent.build(
                code=str(fields.get("code") or "UNKNOWN"),
                message=str(fields.get("message") or ""),
                details=fields.get("details"),
                source=str(fields.get("source") or "backend"),
                severity=str(fields.get("severity") or "error"),
                frames=list(fields.get("frames") or []),
                **context,
            )
        )

    def _on_error_event(self, payload: dict[str, Any]) -> None:
        """Report a journal entry, or offer opt-in while reporting is still off."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - no loop outside the plugin runtime
            return
        if not self.reporter.enabled():
            self._maybe_nudge(loop)
            return
        self._track(loop.create_task(self.reporter.maybe_send(payload)))

    def _maybe_nudge(self, loop: asyncio.AbstractEventLoop) -> None:
        """Offer opt-in after an error, at most once per window, until answered."""
        if self.settings.get("errorReportingNudgeDismissed", False):
            return
        now = time.monotonic()
        if self._last_nudge_at is not None and now - self._last_nudge_at < NUDGE_THROTTLE_SECONDS:
            return
        self._last_nudge_at = now
        self._track(loop.create_task(self.emit(events.ERROR, {"nudge": True})))

    def _track(self, task: asyncio.Task) -> None:
        self._report_tasks.add(task)
        task.add_done_callback(self._report_tasks.discard)

    def runtime_info(self) -> dict[str, Any]:
        import platform as _platform

        info: dict[str, Any] = {
            "pluginVersion": __version__,
            "python": _platform.python_version(),
            "platform": f"{_platform.system()} {_platform.machine()}",
        }
        decky_version = os.environ.get("DECKY_VERSION")
        if decky_version:
            info["decky"] = decky_version
        status = self._last_engine_status
        if status is not None:
            info["engine"] = f"{status.engine_id} {status.version}".strip() if status.version else status.engine_id
            info["engineState"] = status.state
        return info

    def journal_payload(self, limit: int = 50) -> dict[str, Any]:
        return {
            "events": self.journal.events(limit),
            "summary": self.journal.summary(),
            "journalPath": str(self.store.path("error-journal.json")),
        }

    def clear_journal(self) -> dict[str, Any]:
        self.journal.clear()
        return self.journal_payload()

    def record_frontend_error(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Accept an error reported by the UI (a crash, or an unhandled rejection)."""
        details = payload.get("details")
        if details in (None, "") and payload.get("stack"):
            details = payload.get("stack")
        event = ErrorEvent.build(
            code=str(payload.get("code") or "UI_ERROR")[:80],
            message=str(payload.get("message") or "The interface reported an error."),
            details=str(details)[:4000] if details else None,
            source="frontend",
            severity=str(payload.get("severity") or "error"),
            view=payload.get("view"),
        )
        return self.journal.record(event)

    def reporting_payload(self) -> dict[str, Any]:
        return {
            "status": self.reporter.status(),
            "preview": self.reporter.preview(),
            "journal": self.journal.summary(),
        }

    async def send_test_report(self) -> dict[str, Any]:
        result = await self.reporter.send_test()
        return {"result": result, "status": self.reporter.status()}

    def shutdown(self) -> None:
        """Detach the error sink and stop pending reports."""
        set_error_sink(None)
        for task in list(self._report_tasks):
            if not task.done():
                task.cancel()
        self._report_tasks.clear()

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
        # Opting in answers the prompt: never nudge again, even if reporting is
        # later turned back off.
        if values.get("enableErrorReporting"):
            values = {**values, "errorReportingNudgeDismissed": True}
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
