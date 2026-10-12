"""TukUI addon provider.

``api.tukui.org/v1`` is public and keyless, and serves the two TukUI projects
(ElvUI and Tukui). There is no search endpoint, so search is unsupported here;
installed-list and install work still flow through the engine.
"""

from __future__ import annotations

from ..addons.models import PROVIDER_TUKUI, Addon
from ..errors import ADDON_NOT_FOUND, AzerothAddonsError
from .base import AddonProvider
from .http import fetch_json
from .models import ProviderCapabilities, ProviderDownload, ProviderStatus, ProviderVersion

TUKUI_API = "https://api.tukui.org/v1"

CATALOG: dict[str, str] = {
    "elvui": "ElvUI",
    "tukui": "Tukui",
}


def _first(mapping: dict, *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class TukUIProvider(AddonProvider):
    provider_id = PROVIDER_TUKUI
    display_name = "TukUI"
    requires_credential = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=False, metadata=True, versions=True, downloads=True)

    async def _project(self, provider_id: str) -> dict:
        slug = provider_id.lower()
        if slug not in CATALOG:
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "TukUI only distributes ElvUI and Tukui.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )
        payload = await fetch_json(f"{TUKUI_API}/addon/{slug}", provider=self.provider_id, timeout=10.0)
        if not isinstance(payload, dict):
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "That TukUI project was not found.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )
        return payload

    async def health(self) -> ProviderStatus:
        status = ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            capabilities=self.capabilities(),
            available=True,
            state="available",
        )
        try:
            await fetch_json(f"{TUKUI_API}/addon/elvui", provider=self.provider_id, timeout=8.0)
        except Exception as exc:  # noqa: BLE001 - degraded, not fatal
            status.available = False
            status.state = "degraded"
            status.message = "TukUI could not be reached."
            status.detail = getattr(exc, "details", None) or str(exc)
        return status

    async def get_addon(self, provider_id: str) -> Addon | None:
        payload = await self._project(provider_id)
        slug = provider_id.lower()
        return self._addon(
            slug,
            name=CATALOG[slug],
            homepage=f"https://www.tukui.org/addons.php",
            available_version=_first(payload, "version"),
        )

    async def get_versions(self, provider_id: str, *, flavour: str | None = None) -> list[ProviderVersion]:
        payload = await self._project(provider_id)
        version = _first(payload, "version")
        download = _first(payload, "url", "download", "direct")
        patches = payload.get("patch") if isinstance(payload.get("patch"), list) else []
        return [
            ProviderVersion(
                id=version or provider_id,
                version=version,
                released_at=_first(payload, "last_update", "updated_at"),
                channel="stable",
                game_flavours=[str(item) for item in patches if isinstance(item, str)],
                download_url=download,
            )
        ]

    async def resolve_download(self, provider_id: str, version_id: str | None = None) -> ProviderDownload:
        payload = await self._project(provider_id)
        url = _first(payload, "url", "download", "direct")
        if not url:
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "TukUI did not provide a download link.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )
        return ProviderDownload(url=url, filename=f"{provider_id}.zip")
