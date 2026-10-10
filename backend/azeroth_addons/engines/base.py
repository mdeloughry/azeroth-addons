"""The addon-engine interface.

An *engine* owns addon installation state: it installs, updates, removes,
reconciles and rolls back addons inside a specific WoW installation.

instawow is the default engine, not the architecture. Any future engine
(``NativeAddonEngine``, an external manager adapter, ...) implements this same
interface and the rest of the application keeps working.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..addons.models import Addon
from ..installations.models import WowInstallation

# Engine lifecycle states surfaced to the UI.
STATE_UNKNOWN = "unknown"
STATE_MISSING = "missing"
STATE_VERIFYING = "verifying"
STATE_WARMING = "warming"
STATE_READY = "ready"
STATE_INCOMPATIBLE = "incompatible"
STATE_ERROR = "error"


@dataclass(frozen=True)
class EngineCapabilities:
    install: bool = False
    update: bool = False
    remove: bool = False
    reconcile: bool = False
    rollback: bool = False
    search: bool = False
    list_installed: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "install": self.install,
            "update": self.update,
            "remove": self.remove,
            "reconcile": self.reconcile,
            "rollback": self.rollback,
            "search": self.search,
            "listInstalled": self.list_installed,
        }


@dataclass
class EngineStatus:
    engine_id: str
    display_name: str
    state: str = STATE_UNKNOWN
    available: bool = False
    version: str | None = None
    bundled_version: str | None = None
    message: str | None = None
    detail: str | None = None
    capabilities: EngineCapabilities = field(default_factory=EngineCapabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.engine_id,
            "displayName": self.display_name,
            "state": self.state,
            "available": self.available,
            "version": self.version,
            "bundledVersion": self.bundled_version,
            "message": self.message,
            "detail": self.detail,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass
class ReconcileResult:
    managed: list[Addon] = field(default_factory=list)
    unmanaged: list[Addon] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "managed": [addon.to_dict() for addon in self.managed],
            "unmanaged": [addon.to_dict() for addon in self.unmanaged],
            "managedCount": len(self.managed),
            "unmanagedCount": len(self.unmanaged),
        }


class AddonEngine(ABC):
    engine_id: str = "engine"
    display_name: str = "Engine"

    # --- lifecycle ---------------------------------------------------------

    @abstractmethod
    def capabilities(self) -> EngineCapabilities:
        """What this engine can currently do."""

    @abstractmethod
    async def status(self) -> EngineStatus:
        """Current health, without performing expensive work."""

    @abstractmethod
    async def prepare(self) -> EngineStatus:
        """Verify the engine runtime and warm it up. Safe to call repeatedly."""

    # --- addon state -------------------------------------------------------

    @abstractmethod
    async def list_installed(self, installation: WowInstallation) -> list[Addon]:
        ...

    @abstractmethod
    async def reconcile(self, installation: WowInstallation) -> ReconcileResult:
        ...

    @abstractmethod
    async def check_updates(self, installation: WowInstallation) -> list[Addon]:
        ...

    # --- mutations ---------------------------------------------------------

    @abstractmethod
    async def install(
        self,
        installation: WowInstallation,
        provider: str,
        provider_id: str,
        *,
        replace: bool = False,
    ) -> Addon:
        ...

    @abstractmethod
    async def update(self, installation: WowInstallation, addon: Addon) -> Addon:
        ...

    @abstractmethod
    async def update_all(self, installation: WowInstallation) -> list[Addon]:
        ...

    @abstractmethod
    async def remove(self, installation: WowInstallation, addon: Addon) -> None:
        ...

    @abstractmethod
    async def rollback(self, installation: WowInstallation, addon: Addon) -> Addon:
        ...

    # --- discovery ---------------------------------------------------------

    @abstractmethod
    async def search(
        self,
        installation: WowInstallation,
        query: str,
        *,
        limit: int = 25,
    ) -> list[Addon]:
        ...

    # --- helpers -----------------------------------------------------------

    async def search_many(
        self,
        installation: WowInstallation,
        queries: Sequence[str],
        *,
        limit: int = 25,
    ) -> list[Addon]:
        results: list[Addon] = []
        for query in queries:
            results.extend(await self.search(installation, query, limit=limit))
        return results
