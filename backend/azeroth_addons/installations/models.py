"""Domain model for a WoW installation.

A WoW *installation* is one game version directory (``_retail_``,
``_classic_era_``, ...) inside one WoW root. A root containing several
versions therefore yields several installations, and multiple copies of the
same version on different drives are all kept as separate installations.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..security import addons_path_for, canonical, looks_like_version_dir
from .flavours import flavour_label, normalise_flavour

EXECUTABLE_NAMES = ("Wow.exe", "WowClassic.exe")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def make_installation_id(flavour: str, root_path: str) -> str:
    digest = hashlib.sha1(str(canonical(root_path)).encode("utf-8")).hexdigest()[:6]
    return f"{flavour}-{digest}"


def location_label(root_path: str) -> str:
    """Human label describing where an installation lives."""
    text = str(canonical(root_path))
    if text.startswith("/run/media/") or text.startswith("/mnt/"):
        parts = [part for part in text.split("/") if part]
        # /run/media/<user>/<drive>/... -> the drive is the useful part
        drive = parts[3] if len(parts) > 3 and parts[1] == "media" else "External"
        return f"External ({drive})"
    if "/pfx/drive_c/" in text:
        return "Proton"
    if "/.var/app/" in text:
        return "Flatpak"
    return "Internal"


def find_executable(root_path: str) -> str | None:
    root = canonical(root_path)
    for name in EXECUTABLE_NAMES:
        candidate = root / name
        if candidate.exists():
            return str(candidate)
    return None


@dataclass
class WowInstallation:
    id: str
    display_name: str
    flavour: str
    source: str
    root_path: str
    addons_path: str
    available: bool = True
    engine_profile: str = ""
    executable_path: str | None = None
    # Internal, engine-facing metadata. Not part of the frontend payload.
    instawow_flavour: str | None = None
    product_code: str | None = None
    version_folder: str = ""
    created_at: str = field(default_factory=_now)
    last_seen_at: str = field(default_factory=_now)

    # --- derived -----------------------------------------------------------
    @property
    def flavour_label(self) -> str:
        return flavour_label(self.flavour)

    @property
    def interface_dir(self) -> str:
        return str(canonical(self.root_path) / "Interface")

    def refresh_availability(self) -> bool:
        """Recompute ``available`` from the filesystem. Returns True if it changed."""
        previous = self.available
        self.available = looks_like_version_dir(self.root_path)
        if self.available:
            self.last_seen_at = _now()
        return previous != self.available

    # --- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Frontend payload - deliberately free of engine/provider internals."""
        return {
            "id": self.id,
            "displayName": self.display_name,
            "flavour": self.flavour,
            "flavourLabel": self.flavour_label,
            "source": self.source,
            "rootPath": self.root_path,
            "addonsPath": self.addons_path,
            "executablePath": self.executable_path,
            "available": self.available,
            "engineProfile": self.engine_profile,
            "locationLabel": location_label(self.root_path),
            "versionFolder": self.version_folder,
        }

    def to_record(self) -> dict[str, Any]:
        record = self.to_dict()
        record.update(
            {
                "instawowFlavour": self.instawow_flavour,
                "productCode": self.product_code,
                "createdAt": self.created_at,
                "lastSeenAt": self.last_seen_at,
            }
        )
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "WowInstallation":
        root_path = str(record.get("rootPath") or "")
        flavour = normalise_flavour(record.get("flavour"))
        installation_id = str(record.get("id") or make_installation_id(flavour, root_path))
        return cls(
            id=installation_id,
            display_name=str(record.get("displayName") or f"{flavour_label(flavour)}"),
            flavour=flavour,
            source=str(record.get("source") or "auto"),
            root_path=root_path,
            addons_path=str(record.get("addonsPath") or addons_path_for(root_path)),
            available=bool(record.get("available", True)),
            engine_profile=str(record.get("engineProfile") or f"az-{installation_id}"),
            executable_path=record.get("executablePath"),
            instawow_flavour=record.get("instawowFlavour"),
            product_code=record.get("productCode"),
            version_folder=str(record.get("versionFolder") or ""),
            created_at=str(record.get("createdAt") or _now()),
            last_seen_at=str(record.get("lastSeenAt") or _now()),
        )

    @classmethod
    def create(
        cls,
        *,
        root_path: str,
        flavour: str,
        display_name: str,
        source: str = "auto",
        version_folder: str = "",
        instawow_flavour: str | None = None,
        product_code: str | None = None,
    ) -> "WowInstallation":
        flavour = normalise_flavour(flavour)
        installation_id = make_installation_id(flavour, root_path)
        return cls(
            id=installation_id,
            display_name=display_name,
            flavour=flavour,
            source=source,
            root_path=str(canonical(root_path)),
            addons_path=str(addons_path_for(root_path)),
            available=looks_like_version_dir(root_path),
            engine_profile=f"az-{installation_id}",
            executable_path=find_executable(root_path),
            instawow_flavour=instawow_flavour,
            product_code=product_code,
            version_folder=version_folder,
        )
