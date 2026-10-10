"""Provider-facing transfer objects.

These are *provider* models (metadata, versions, downloads), distinct from the
*engine* concept of installed addon state. Providers may supply:

* metadata, search, compatibility information, releases, download information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderCapabilities:
    search: bool = False
    metadata: bool = False
    versions: bool = False
    downloads: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "search": self.search,
            "metadata": self.metadata,
            "versions": self.versions,
            "downloads": self.downloads,
        }


@dataclass
class ProviderVersion:
    id: str
    version: str | None = None
    released_at: str | None = None
    channel: str | None = None
    game_flavours: list[str] = field(default_factory=list)
    download_url: str | None = None
    filename: str | None = None
    size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "releasedAt": self.released_at,
            "channel": self.channel,
            "gameFlavours": list(self.game_flavours),
            "downloadUrl": self.download_url,
            "filename": self.filename,
            "size": self.size,
        }


@dataclass
class ProviderDownload:
    url: str
    filename: str | None = None
    size: int | None = None
    expires_at: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "filename": self.filename,
            "size": self.size,
            "expiresAt": self.expires_at,
        }


@dataclass
class ProviderStatus:
    provider_id: str
    display_name: str
    available: bool = False
    state: str = "unavailable"
    message: str | None = None
    detail: str | None = None
    requires_credential: bool = False
    credential_configured: bool = False
    credential_mode: str = "disabled"
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "displayName": self.display_name,
            "available": self.available,
            "state": self.state,
            "message": self.message,
            "detail": self.detail,
            "requiresCredential": self.requires_credential,
            "credentialConfigured": self.credential_configured,
            "credentialMode": self.credential_mode,
            "capabilities": self.capabilities.to_dict(),
        }
