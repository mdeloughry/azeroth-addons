"""The provider-neutral addon model.

The UI only ever sees this shape. Raw CurseForge ids, instawow package
structures and provider response formats stay behind the engine/provider
interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Addon state machine, mirrored by the frontend type.
STATE_CURRENT = "current"
STATE_UPDATE_AVAILABLE = "update-available"
STATE_INSTALLING = "installing"
STATE_UPDATING = "updating"
STATE_UNMANAGED = "unmanaged"
STATE_ERROR = "error"

ADDON_STATES = (
    STATE_CURRENT,
    STATE_UPDATE_AVAILABLE,
    STATE_INSTALLING,
    STATE_UPDATING,
    STATE_UNMANAGED,
    STATE_ERROR,
)

# Our provider identifiers (distinct from engine-specific source ids).
PROVIDER_CURSEFORGE = "curseforge"
PROVIDER_GITHUB = "github"
PROVIDER_WAGO = "wago"
PROVIDER_WOWINTERFACE = "wowinterface"
PROVIDER_TUKUI = "tukui"
PROVIDER_INSTAWOW = "instawow"

PROVIDER_LABELS = {
    PROVIDER_CURSEFORGE: "CurseForge",
    PROVIDER_GITHUB: "GitHub",
    PROVIDER_WAGO: "Wago",
    PROVIDER_WOWINTERFACE: "WoWInterface",
    PROVIDER_TUKUI: "TukUI",
    PROVIDER_INSTAWOW: "instawow",
}

KNOWN_PROVIDERS = tuple(PROVIDER_LABELS)


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider.title() if provider else "Unknown")


def addon_key(provider: str, provider_id: str) -> str:
    """Stable, provider-qualified identity.

    Same-named addons from different providers are different packages and are
    never merged implicitly.
    """
    return f"{provider}:{provider_id}"


@dataclass
class Addon:
    id: str
    name: str
    provider: str
    provider_id: str
    description: str | None = None
    installed_version: str | None = None
    available_version: str | None = None
    homepage: str | None = None
    game_flavours: list[str] = field(default_factory=list)
    state: str = STATE_CURRENT
    error: str | None = None
    folder_name: str | None = None
    pinned: bool = False
    download_url: str | None = None

    @property
    def provider_label(self) -> str:
        return provider_label(self.provider)

    @property
    def display_name(self) -> str:
        return self.name or self.provider_id or self.folder_name or self.id

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.display_name,
            "provider": self.provider,
            "providerLabel": self.provider_label,
            "providerId": self.provider_id,
            "state": self.state,
            "gameFlavours": list(self.game_flavours),
            "pinned": self.pinned,
        }
        optional = {
            "description": self.description,
            "installedVersion": self.installed_version,
            "availableVersion": self.available_version,
            "homepage": self.homepage,
            "error": self.error,
            "folderName": self.folder_name,
            "downloadUrl": self.download_url,
        }
        for key, value in optional.items():
            if value:
                payload[key] = value
        return payload


@dataclass
class AddonDefinition:
    """What the frontend asks the backend to install."""

    provider: str
    provider_id: str

    @property
    def key(self) -> str:
        return addon_key(self.provider, self.provider_id)

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "providerId": self.provider_id, "id": self.key}


def addon_from_engine(
    *,
    provider: str,
    provider_id: str,
    version: str | None,
    name: str | None = None,
    folder_name: str | None = None,
    pinned: bool = False,
    game_flavours: list[str] | None = None,
) -> Addon:
    return Addon(
        id=addon_key(provider, provider_id),
        name=name or provider_id,
        provider=provider,
        provider_id=provider_id,
        installed_version=version,
        folder_name=folder_name,
        pinned=pinned,
        game_flavours=list(game_flavours or []),
    )


def unmanaged_addon(folder_name: str, flavour: str | None = None) -> Addon:
    """An addon folder Azeroth Addons did not install. Left strictly alone."""
    return Addon(
        id=f"unmanaged:{folder_name}",
        name=folder_name,
        provider="unmanaged",
        provider_id=folder_name,
        state=STATE_UNMANAGED,
        folder_name=folder_name,
        game_flavours=[flavour] if flavour else [],
    )
