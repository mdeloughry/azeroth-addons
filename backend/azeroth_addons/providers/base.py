"""The addon-provider interface.

A *provider* is a source of addon data: search, metadata, versions and
download information. This is deliberately separate from the *engine* concept:

    CurseForge  = source/provider
    instawow    = addon-management engine

Providers return the provider-neutral :class:`Addon` model so the UI never
learns provider-specific response formats.
"""

from __future__ import annotations

from abc import ABC
from typing import Sequence

from ..addons.models import Addon, provider_label
from ..errors import PROVIDER_UNAVAILABLE, AzerothAddonsError
from .models import (
    ProviderCapabilities,
    ProviderDownload,
    ProviderStatus,
    ProviderVersion,
)


class AddonProvider(ABC):
    provider_id: str = "provider"
    display_name: str = "Provider"
    requires_credential: bool = False
    credential_key: str | None = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def credential(self) -> str | None:
        """Return the configured credential, if any. Never logged."""
        return None

    def credential_mode(self) -> str:
        return "configured" if self.credential() else "disabled"

    def is_enabled(self) -> bool:
        return True

    async def health(self) -> ProviderStatus:
        """Cheap, non-network health signal. Override to probe the provider."""
        capabilities = self.capabilities()
        enabled = self.is_enabled()
        credential = self.credential()
        status = ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            available=enabled,
            state="available" if enabled else "unavailable",
            requires_credential=self.requires_credential,
            credential_configured=bool(credential),
            credential_mode=self.credential_mode(),
            capabilities=capabilities,
        )
        if not enabled:
            status.message = "Not configured."
        elif self.requires_credential and not credential:
            status.available = False
            status.state = "not-configured"
            status.message = "A credential is required."
        return status

    def not_supported(self, feature: str) -> AzerothAddonsError:
        return AzerothAddonsError(
            PROVIDER_UNAVAILABLE,
            f"{self.display_name} does not support {feature}.",
            provider=self.provider_id,
        )

    # --- read operations ---------------------------------------------------

    async def search(self, query: str, *, flavour: str | None = None, limit: int = 25) -> list[Addon]:
        raise self.not_supported("search")

    async def get_addon(self, provider_id: str) -> Addon | None:
        raise self.not_supported("metadata")

    async def get_versions(self, provider_id: str, *, flavour: str | None = None) -> list[ProviderVersion]:
        raise self.not_supported("version listings")

    async def resolve_download(self, provider_id: str, version_id: str | None = None) -> ProviderDownload:
        raise self.not_supported("downloads")

    async def get_addons(self, provider_ids: Sequence[str]) -> list[Addon]:
        out: list[Addon] = []
        for provider_id in provider_ids:
            addon = await self.get_addon(provider_id)
            if addon is not None:
                out.append(addon)
        return out

    # --- helpers -----------------------------------------------------------

    def _addon(
        self,
        provider_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        homepage: str | None = None,
        installed_version: str | None = None,
        available_version: str | None = None,
        game_flavours: Sequence[str] | None = None,
    ) -> Addon:
        return Addon(
            id=f"{self.provider_id}:{provider_id}",
            name=name or provider_id,
            provider=self.provider_id,
            provider_id=provider_id,
            description=description,
            homepage=homepage,
            installed_version=installed_version,
            available_version=available_version,
            game_flavours=list(game_flavours or []),
        )

    @property
    def label(self) -> str:
        return provider_label(self.provider_id)
