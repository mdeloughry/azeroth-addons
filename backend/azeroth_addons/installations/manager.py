"""Installation registry.

Persists every known WoW installation, keeps availability fresh, and merges
newly discovered installations without ever silently dropping existing ones
(a missing SD card must not delete its installation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..errors import (
    DUPLICATE_INSTALLATION,
    INSTALLATION_NOT_FOUND,
    INSTALLATION_UNAVAILABLE,
    INVALID_WOW_PATH,
    AzerothAddonsError,
)
from ..logctx import ctx, get_logger
from ..security import canonical, validate_installation_root
from ..settings import InstallationStore, SettingsStore
from .discovery import Discovered, DiscoveryEnvironment, default_environment, discover, discover_path
from .models import WowInstallation, location_label

logger = get_logger()


@dataclass
class SyncResult:
    added: list[WowInstallation] = field(default_factory=list)
    restored: list[WowInstallation] = field(default_factory=list)
    unavailable: list[WowInstallation] = field(default_factory=list)
    unchanged: int = 0
    scanned_roots: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": [inst.to_dict() for inst in self.added],
            "restored": [inst.to_dict() for inst in self.restored],
            "unavailable": [inst.to_dict() for inst in self.unavailable],
            "unchanged": self.unchanged,
            "scannedRoots": self.scanned_roots,
            "total": len(self.added) + len(self.restored) + len(self.unavailable) + self.unchanged,
        }


class InstallationManager:
    def __init__(self, store: InstallationStore, settings: SettingsStore) -> None:
        self._store = store
        self._settings = settings
        self._installations: dict[str, WowInstallation] = {}
        self._load()

    # --- persistence -------------------------------------------------------

    def _load(self) -> None:
        self._installations = {}
        for record in self._store.load():
            try:
                installation = WowInstallation.from_record(record)
            except Exception as exc:  # noqa: BLE001 - a bad record must not break startup
                logger.warning("skipping malformed installation record: %s", exc)
                continue
            if not installation.engine_profile:
                installation.engine_profile = f"az-{installation.id}"
            # Availability is always recomputed from the filesystem: an SD card
            # that was unplugged while the plugin was stopped must read as
            # unavailable, and a reconnected drive must heal automatically.
            installation.refresh_availability()
            self._installations[installation.id] = installation
        logger.info("loaded %d installation(s) from disk", len(self._installations))

    def save(self) -> None:
        self._store.save([inst.to_record() for inst in self._installations.values()])

    # --- reads -------------------------------------------------------------

    def all(self) -> list[WowInstallation]:
        return sorted(
            self._installations.values(),
            key=lambda inst: (not inst.available, inst.flavour, inst.display_name),
        )

    def available(self) -> list[WowInstallation]:
        return [inst for inst in self.all() if inst.available]

    def get(self, installation_id: str) -> WowInstallation:
        installation = self._installations.get(installation_id)
        if installation is None:
            raise AzerothAddonsError(
                INSTALLATION_NOT_FOUND,
                "That World of Warcraft installation is not registered.",
                installation_id=installation_id,
            )
        return installation

    def get_or_none(self, installation_id: str | None) -> WowInstallation | None:
        if not installation_id:
            return None
        return self._installations.get(installation_id)

    def require_available(self, installation_id: str) -> WowInstallation:
        installation = self.get(installation_id)
        if not installation.available:
            raise AzerothAddonsError(
                INSTALLATION_UNAVAILABLE,
                f"{installation.display_name} is not available right now. Is its drive connected?",
                installation_id=installation.id,
                details=f"root={installation.root_path}",
            )
        return installation

    # --- selection ---------------------------------------------------------

    def selected_id(self) -> str | None:
        selected = self._settings.get("selectedInstallationId")
        if selected and selected in self._installations:
            return selected
        fallback = next((inst.id for inst in self.available()), None)
        if fallback is None:
            fallback = next((inst.id for inst in self.all()), None)
        return fallback

    def set_selected(self, installation_id: str | None) -> str | None:
        if installation_id:
            self.get(installation_id)  # validate
        self._settings.set("selectedInstallationId", installation_id)
        return installation_id

    # --- mutation ----------------------------------------------------------

    def register_discovered(self, item: Discovered, source: str = "auto") -> tuple[WowInstallation, bool]:
        """Add (or refresh) an installation. Returns ``(installation, created)``."""
        key = str(canonical(item.root_path))
        for existing in self._installations.values():
            if str(canonical(existing.root_path)) == key:
                existing.refresh_availability()
                return existing, False

        installation = WowInstallation.create(
            root_path=item.root_path,
            flavour=item.flavour,
            display_name=self._unique_name(item.label, location_label(item.root_path)),
            source=source,
            version_folder=item.version_folder,
            instawow_flavour=item.instawow_flavour,
            product_code=item.product_code,
        )
        self._installations[installation.id] = installation
        return installation, True

    def _unique_name(self, label: str, location: str) -> str:
        base = f"{label} - {location}"
        taken = {inst.display_name for inst in self._installations.values()}
        if base not in taken:
            return base
        counter = 2
        while f"{base} {counter}" in taken:
            counter += 1
        return f"{base} {counter}"

    def add_custom(self, path: str | os.PathLike[str]) -> dict[str, Any]:
        """Register installations found under a user-chosen path."""
        root = validate_installation_root(path)
        found = discover_path(root)
        if not found:
            raise AzerothAddonsError(
                INVALID_WOW_PATH,
                "No World of Warcraft installation was found in that folder.",
                details=f"path={root}",
            )

        added: list[WowInstallation] = []
        existing: list[WowInstallation] = []
        for item in found:
            installation, created = self.register_discovered(item, source="custom")
            (added if created else existing).append(installation)
        if added:
            self.save()
        logger.info(
            "add_custom %s added=%d existing=%d",
            ctx(operation="add_installation"),
            len(added),
            len(existing),
        )
        return {
            "added": [inst.to_dict() for inst in added],
            "existing": [inst.to_dict() for inst in existing],
            "discovered": len(found),
        }

    def rescan(self, env: DiscoveryEnvironment | None = None) -> SyncResult:
        """Discover new installations and refresh availability of known ones."""
        env = env or default_environment()
        result = SyncResult()
        for existing in list(self._installations.values()):
            was = existing.available
            existing.refresh_availability()
            if was and not existing.available:
                result.unavailable.append(existing)
            elif not was and existing.available:
                result.restored.append(existing)

        for item in discover(env):
            installation, created = self.register_discovered(item, source="auto")
            if created:
                result.added.append(installation)
            else:
                result.unchanged += 1

        result.scanned_roots = len(env.all_scan_roots())
        self.save()
        logger.info(
            "rescan %s added=%d restored=%d unavailable=%d unchanged=%d",
            ctx(operation="rescan"),
            len(result.added),
            len(result.restored),
            len(result.unavailable),
            result.unchanged,
        )
        return result

    def refresh_availability(self) -> list[WowInstallation]:
        changed: list[WowInstallation] = []
        for installation in self._installations.values():
            if installation.refresh_availability():
                changed.append(installation)
        return changed

    def rename(self, installation_id: str, display_name: str) -> WowInstallation:
        installation = self.get(installation_id)
        clean = (display_name or "").strip()
        if not clean:
            raise AzerothAddonsError("INVALID_ARGUMENT", "A display name is required.")
        if len(clean) > 80:
            clean = clean[:80]
        installation.display_name = clean
        self.save()
        return installation

    def remove(self, installation_id: str) -> WowInstallation:
        installation = self.get(installation_id)
        del self._installations[installation_id]
        if self._settings.get("selectedInstallationId") == installation_id:
            self._settings.set("selectedInstallationId", None)
        self.save()
        logger.info(
            "removed installation %s",
            ctx(installation=installation_id, operation="remove_installation"),
        )
        return installation

    def duplicate_of(self, root_path: str) -> WowInstallation | None:
        key = str(canonical(root_path))
        for existing in self._installations.values():
            if str(canonical(existing.root_path)) == key:
                return existing
        return None

    def assert_not_duplicate(self, root_path: str) -> None:
        duplicate = self.duplicate_of(root_path)
        if duplicate is not None:
            raise AzerothAddonsError(
                DUPLICATE_INSTALLATION,
                f"{duplicate.display_name} is already registered.",
                installation_id=duplicate.id,
            )

    def count_by_flavour(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for installation in self._installations.values():
            counts[installation.flavour] = counts.get(installation.flavour, 0) + 1
        return counts

    def summary(self) -> dict[str, Any]:
        installations = self.all()
        return {
            "total": len(installations),
            "available": sum(1 for inst in installations if inst.available),
            "byFlavour": self.count_by_flavour(),
            "selectedId": self.selected_id(),
        }
