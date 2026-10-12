"""Addon operations, orchestration and safety gates.

This is the layer the RPC surface talks to. It owns:

* resolving an ``installation_id`` to a registered installation;
* refusing to touch a protected path (via :mod:`azeroth_addons.security`);
* refusing to mutate a running WoW installation (per installation, not globally);
* progress events so the UI can show "2 / 5" while work happens;
* a short-lived cache so the UI can poll cheaply.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Sequence

from ..engines.base import EngineStatus
from ..engines.registry import EngineRegistry
from ..errors import (
    ADDON_NOT_FOUND,
    ENGINE_UNSUPPORTED,
    PROVIDER_UNAVAILABLE,
    WOW_RUNNING,
    AzerothAddonsError,
)
from ..installations.manager import InstallationManager
from ..installations.models import WowInstallation
from ..logctx import ctx, get_logger
from ..process_detection import running_installation_ids
from ..providers.registry import ProviderRegistry
from ..security import canonical, validate_addons_target
from ..settings import SettingsStore
from .. import events
from .models import Addon, STATE_UPDATE_AVAILABLE

logger = get_logger()

Emitter = Callable[[str, Any], Awaitable[None]]
CACHE_TTL_SECONDS = 30.0


async def _noop_emit(event: str, payload: Any = None) -> None:  # pragma: no cover - default
    return None


class AddonService:
    def __init__(
        self,
        installations: InstallationManager,
        engines: EngineRegistry,
        providers: ProviderRegistry,
        settings: SettingsStore,
        *,
        emit: Emitter | None = None,
        proc_root: str = "/proc",
    ) -> None:
        self._installations = installations
        self._engines = engines
        self._providers = providers
        self._settings = settings
        self._emit = emit or _noop_emit
        self._proc_root = proc_root
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # --- helpers -----------------------------------------------------------

    async def _fire(self, event: str, payload: Any) -> None:
        try:
            await self._emit(event, payload)
        except Exception as exc:  # noqa: BLE001 - a failed event must not fail the operation
            logger.debug("event %s failed: %s", event, exc)

    def resolve(self, installation_id: str) -> WowInstallation:
        return self._installations.require_available(installation_id)

    def is_running(self, installation: WowInstallation) -> bool:
        return installation.id in running_installation_ids([installation], self._proc_root)

    def running_ids(self) -> set[str]:
        return running_installation_ids(self._installations.all(), self._proc_root)

    def _assert_writable(self, installation: WowInstallation, operation: str) -> None:
        """Canonicalise the target and refuse to touch a running installation."""
        validate_addons_target(installation.addons_path, installation.root_path)
        if self.is_running(installation):
            raise AzerothAddonsError(
                WOW_RUNNING,
                f"{installation.display_name} is currently running. "
                f"Close {installation.flavour_label} before changing its addons.",
                installation_id=installation.id,
                details=f"operation={operation}",
            )

    def _invalidate(self, installation_id: str) -> None:
        self._cache.pop(installation_id, None)

    def invalidate(self, installation_id: str | None = None) -> None:
        """Drop cached state for one installation, or all of them."""
        if installation_id is None:
            self._cache.clear()
        else:
            self._invalidate(installation_id)

    def _engine(self):
        return self._engines.get()

    async def _progress(
        self,
        installation: WowInstallation,
        kind: str,
        *,
        current: int = 0,
        total: int = 0,
        phase: str = "running",
        addon: Addon | None = None,
        message: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "installationId": installation.id,
            "kind": kind,
            "phase": phase,
            "current": current,
            "total": total,
        }
        if addon is not None:
            payload["addon"] = addon.to_dict()
        if message:
            payload["message"] = message
        await self._fire(events.OPERATION, payload)

    # --- runtime / status --------------------------------------------------

    async def prepare_engine(self) -> EngineStatus:
        engine = self._engine()
        status = await engine.prepare()
        await self._fire(events.RUNTIME_STATUS, self.runtime_status(status))
        return status

    async def engine_statuses(self) -> list[dict[str, Any]]:
        return [status.to_dict() for status in await self._engines.statuses()]

    async def provider_statuses(self) -> list[dict[str, Any]]:
        return [status.to_dict() | self._engine().source_access(status.provider_id) for status in await self._providers.statuses()]

    def runtime_status(self, engine_status: EngineStatus | None = None) -> dict[str, Any]:
        return {
            "pluginVersion": _plugin_version(),
            "engine": engine_status.to_dict() if engine_status else None,
            "installations": self._installations.summary(),
            "running": sorted(self.running_ids()),
        }

    def installations_payload(self) -> list[dict[str, Any]]:
        return [installation.to_dict() for installation in self._installations.all()]

    async def installations_changed(self) -> None:
        await self._fire(events.INSTALLATIONS_CHANGED, self.installations_payload())

    # --- reads -------------------------------------------------------------

    async def installed(
        self,
        installation_id: str,
        *,
        refresh: bool = False,
        reconcile: bool = True,
    ) -> dict[str, Any]:
        installation = self.resolve(installation_id)

        cached = self._cache.get(installation_id)
        if cached and not refresh and (time.monotonic() - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]

        engine = self._engine()
        if reconcile and engine.capabilities().reconcile:
            result = await engine.reconcile(installation)
            managed, unmanaged = result.managed, result.unmanaged
        else:
            managed, unmanaged = await engine.list_installed(installation), []

        payload = {
            "installationId": installation.id,
            "addons": [addon.to_dict() for addon in managed],
            "unmanaged": [addon.to_dict() for addon in unmanaged],
            "counts": {
                "installed": len(managed),
                "unmanaged": len(unmanaged),
                "updates": 0,
            },
            "running": self.is_running(installation),
            "fetchedAt": time.time(),
        }
        self._cache[installation_id] = (time.monotonic(), payload)
        return payload

    async def installed_addons(self, installation_id: str, *, refresh: bool = False) -> list[Addon]:
        """The managed addon list (used to annotate search results)."""
        installation = self.resolve(installation_id)
        if not refresh:
            cached = self._cache.get(installation_id)
            if cached and (time.monotonic() - cached[0]) < CACHE_TTL_SECONDS:
                return [_addon_from_payload(item) for item in cached[1]["addons"]]
        engine = self._engine()
        addons = await engine.list_installed(installation)
        logger.debug(
            "read installed addons count=%d %s",
            len(addons),
            ctx(installation=installation.id, engine=engine.engine_id, operation="list_installed"),
        )
        return addons

    async def check_updates(self, installation_id: str) -> dict[str, Any]:
        installation = self.resolve(installation_id)
        engine = self._engine()
        if not engine.capabilities().update:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "The addon engine cannot check for updates.",
                installation_id=installation.id,
            )
        updates = await engine.check_updates(installation)

        payload = {
            "installationId": installation.id,
            "updates": [addon.to_dict() for addon in updates],
            "count": len(updates),
        }
        cached = self._cache.get(installation_id)
        if cached:
            cached[1]["counts"]["updates"] = len(updates)
        await self._fire(events.ADDONS_CHANGED, {"installationId": installation.id, "reason": "updates"})
        return payload

    async def reconcile(self, installation_id: str) -> dict[str, Any]:
        self._invalidate(installation_id)
        payload = await self.installed(installation_id, refresh=True, reconcile=True)
        await self._fire(events.ADDONS_CHANGED, {"installationId": installation_id, "reason": "reconcile"})
        return payload

    # --- mutations ---------------------------------------------------------

    async def install(
        self,
        installation_id: str,
        provider: str,
        provider_id: str,
        *,
        replace: bool = False,
    ) -> Addon:
        installation = self.resolve(installation_id)
        self._assert_writable(installation, "install")
        engine = self._engine()
        if not engine.capabilities().install:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "The addon engine cannot install addons.",
                installation_id=installation.id,
                provider=provider,
            )
        access = engine.source_access(provider)
        if not access["downloadAvailable"]:
            raise AzerothAddonsError(
                PROVIDER_UNAVAILABLE,
                "This download source is not configured.",
                provider=provider,
                details=access["setupInstructions"],
            )
        pending = Addon(id=f"{provider}:{provider_id}", name=provider_id, provider=provider, provider_id=provider_id)
        await self._progress(installation, "install", phase="start", addon=pending, message=f"Installing {provider_id}…")
        try:
            addon = await engine.install(installation, provider, provider_id, replace=replace)
        except Exception:
            await self._progress(installation, "install", phase="failed", addon=pending)
            raise
        finally:
            self._invalidate(installation_id)
        await self._progress(installation, "install", phase="done", current=1, total=1, addon=addon)
        await self._fire(
            events.ADDONS_CHANGED,
            {"installationId": installation.id, "reason": "install", "addonId": addon.id},
        )
        return addon

    async def update(self, installation_id: str, addon_id: str) -> Addon:
        installation = self.resolve(installation_id)
        self._assert_writable(installation, "update")
        engine = self._engine()
        addon = await self._require_managed_addon(installation, addon_id)
        await self._progress(installation, "update", phase="start", current=0, total=1, addon=addon)
        try:
            updated = await engine.update(installation, addon)
        finally:
            self._invalidate(installation_id)
        await self._progress(installation, "update", phase="done", current=1, total=1, addon=updated)
        await self._fire(
            events.ADDONS_CHANGED,
            {"installationId": installation.id, "reason": "update", "addonId": addon.id},
        )
        return updated

    async def update_all(self, installation_id: str) -> dict[str, Any]:
        installation = self.resolve(installation_id)
        self._assert_writable(installation, "update_all")
        engine = self._engine()
        if not engine.capabilities().update:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "The addon engine cannot update addons.",
                installation_id=installation.id,
            )

        targets = await engine.check_updates(installation)
        updated: list[Addon] = []
        failures: list[dict[str, Any]] = []

        if targets:
            total = len(targets)
            await self._progress(installation, "update_all", phase="start", current=0, total=total)
            for index, target in enumerate(targets, start=1):
                await self._progress(installation, "update_all", phase="progress", current=index - 1, total=total, addon=target)
                try:
                    result = await engine.update(installation, target)
                    updated.append(result)
                except AzerothAddonsError as exc:
                    failures.append({"addonId": target.id, "error": exc.to_dict()})
                    logger.warning(
                        "update_all: %s failed: %s",
                        target.id,
                        exc.message,
                    )
                await self._progress(
                    installation,
                    "update_all",
                    phase="progress",
                    current=index,
                    total=total,
                    addon=target,
                )
            await self._progress(installation, "update_all", phase="done", current=total, total=total)
        else:
            # We could not enumerate targets from the dry run; ask the engine to
            # update everything and report what changed.
            await self._progress(installation, "update_all", phase="start", current=0, total=0)
            updated = await engine.update_all(installation)
            await self._progress(
                installation, "update_all", phase="done", current=len(updated), total=len(updated)
            )

        self._invalidate(installation_id)
        await self._fire(
            events.ADDONS_CHANGED,
            {"installationId": installation.id, "reason": "update_all"},
        )
        return {
            "installationId": installation.id,
            "updated": [addon.to_dict() for addon in updated],
            "updatedCount": len(updated),
            "failures": failures,
        }

    async def remove(self, installation_id: str, addon_id: str) -> dict[str, Any]:
        installation = self.resolve(installation_id)
        self._assert_writable(installation, "remove")
        engine = self._engine()
        if not engine.capabilities().remove:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "The addon engine cannot remove addons.",
                installation_id=installation.id,
            )
        addon = await self._require_managed_addon(installation, addon_id)
        await self._progress(installation, "remove", phase="start", addon=addon)
        try:
            await engine.remove(installation, addon)
        finally:
            self._invalidate(installation_id)
        await self._progress(installation, "remove", phase="done", current=1, total=1, addon=addon)
        await self._fire(
            events.ADDONS_CHANGED,
            {"installationId": installation.id, "reason": "remove", "addonId": addon.id},
        )
        return {"installationId": installation.id, "removed": addon.to_dict()}

    async def rollback(self, installation_id: str, addon_id: str) -> Addon:
        installation = self.resolve(installation_id)
        self._assert_writable(installation, "rollback")
        engine = self._engine()
        if not engine.capabilities().rollback:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "Rollback is not enabled. Turn on 'Experimental rollback' in Settings.",
                installation_id=installation.id,
            )
        addon = await self._require_managed_addon(installation, addon_id)
        try:
            rolled = await engine.rollback(installation, addon)
        finally:
            self._invalidate(installation_id)
        await self._fire(
            events.ADDONS_CHANGED,
            {"installationId": installation.id, "reason": "rollback", "addonId": addon.id},
        )
        return rolled

    # --- internals ---------------------------------------------------------

    def _addons_from_cache(self, installation_id: str) -> list[Addon]:
        cached = self._cache.get(installation_id)
        if not cached:
            return []
        return [_addon_from_payload(item) for item in cached[1]["addons"]]

    async def _require_managed_addon(self, installation: WowInstallation, addon_id: str) -> Addon:
        addons = self._addons_from_cache(installation.id)
        if not addons:
            engine = self._engine()
            addons = await engine.list_installed(installation)
        for addon in addons:
            if addon.id == addon_id:
                if addon.state == "unmanaged":
                    raise AzerothAddonsError(
                        ADDON_NOT_FOUND,
                        "This addon is not managed by Azeroth Addons, so it will not be modified.",
                        installation_id=installation.id,
                    )
                return addon
        raise AzerothAddonsError(
            ADDON_NOT_FOUND,
            "That addon is not installed in this installation.",
            installation_id=installation.id,
        )

    def lookup_definition(self, installation_id: str, addon_id: str) -> tuple[str, str]:
        """Split a provider-qualified addon id into ``(provider, provider_id)``."""
        for addon in self._addons_from_cache(installation_id):
            if addon.id == addon_id:
                return addon.provider, addon.provider_id
        provider, _, provider_id = addon_id.partition(":")
        if not provider or not provider_id:
            raise AzerothAddonsError(
                "INVALID_ARGUMENT",
                "That addon identifier is not valid.",
                installation_id=installation_id,
                details=f"addonId={addon_id}",
            )
        return provider, provider_id


def _addon_from_payload(payload: dict[str, Any]) -> Addon:
    return Addon(
        id=str(payload.get("id") or ""),
        name=str(payload.get("name") or ""),
        provider=str(payload.get("provider") or ""),
        provider_id=str(payload.get("providerId") or ""),
        description=payload.get("description"),
        last_updated=payload.get("lastUpdated"),
        download_count=payload.get("downloadCount"),
        installed_version=payload.get("installedVersion"),
        available_version=payload.get("availableVersion"),
        homepage=payload.get("homepage"),
        game_flavours=list(payload.get("gameFlavours") or []),
        state=str(payload.get("state") or "current"),
        error=payload.get("error"),
        folder_name=payload.get("folderName"),
        pinned=bool(payload.get("pinned", False)),
    )


def _plugin_version() -> str:
    from .. import __version__

    return __version__


def mark_update_state(addons: Sequence[Addon], updates: Sequence[Addon]) -> None:
    """Annotate an installed list with update availability (never mutates identity)."""
    keys = {(addon.provider, addon.provider_id.lower()) for addon in updates}
    for addon in addons:
        if (addon.provider, addon.provider_id.lower()) in keys:
            addon.state = STATE_UPDATE_AVAILABLE


def canonical_addons_path(installation: WowInstallation) -> str:
    return str(canonical(installation.addons_path))
