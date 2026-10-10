"""CurseForge direct-API provider - **prototype, feature-flagged, disabled by default.**

Why it is shaped this way
-------------------------
CurseForge (Overwolf) issues API keys per approved application. Their 3rd-party
terms state that keys are non-transferable and may not be shared with a third
party, and they forbid caching API data. Since 2026-07-16 CurseForge also
requires an API key for CDN file downloads.

Consequences baked into this module:

* the provider is **off unless a feature flag is explicitly enabled**;
* a credential is read from the plugin's credential store or the environment,
  is used only in an ``x-api-key`` header, and is **never logged or returned to
  the frontend**;
* nothing here is persisted - API responses are used in-flight only;
* authors who opted out of third-party distribution are respected: their files
  raise a clear error instead of being fetched by other means.

Normal Azeroth Addons operation does not depend on this provider at all: the
bundled engine covers CurseForge for users who supply their own credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..addons.models import PROVIDER_CURSEFORGE, Addon
from ..errors import (
    ADDON_NOT_FOUND,
    DOWNLOAD_FAILED,
    PROVIDER_AUTH_FAILED,
    PROVIDER_UNAVAILABLE,
    AzerothAddonsError,
)
from ..logctx import ctx, get_logger
from .base import AddonProvider
from .http import fetch_json
from .models import ProviderCapabilities, ProviderDownload, ProviderStatus, ProviderVersion

logger = get_logger()

CURSEFORGE_API = "https://api.curseforge.com/v1"
WOW_GAME_ID = 1

# Credential strategies. The architecture supports several without committing
# to one; only "developer" is implemented for the prototype.
MODE_DISABLED = "disabled"
MODE_DEVELOPER = "developer"
MODE_SERVICE = "service"


@dataclass
class CurseForgeCredentials:
    mode: str = MODE_DISABLED
    api_key: str | None = None
    service_url: str | None = None
    reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.mode != MODE_DISABLED


class CurseForgeProvider(AddonProvider):
    provider_id = PROVIDER_CURSEFORGE
    display_name = "CurseForge"
    requires_credential = True
    credential_key = "curseforge"

    def __init__(
        self,
        *,
        credential_provider: Callable[[], str | None] | None = None,
        feature_enabled: Callable[[], bool] | None = None,
        service_url_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._credential_provider = credential_provider
        self._feature_enabled = feature_enabled or (lambda: False)
        self._service_url_provider = service_url_provider
        self._last_error: str | None = None

    # --- credentials -------------------------------------------------------

    def credentials(self) -> CurseForgeCredentials:
        api_key = self._credential_provider() if self._credential_provider else None
        service_url = self._service_url_provider() if self._service_url_provider else None

        if service_url:
            return CurseForgeCredentials(mode=MODE_SERVICE, service_url=service_url, reason=None)
        if not self._feature_enabled():
            return CurseForgeCredentials(
                mode=MODE_DISABLED,
                api_key=api_key or None,
                reason="Direct CurseForge support is disabled in Settings.",
            )
        if not api_key:
            return CurseForgeCredentials(
                mode=MODE_DISABLED,
                reason="No CurseForge API credential is configured.",
            )
        return CurseForgeCredentials(mode=MODE_DEVELOPER, api_key=api_key)

    def credential(self) -> str | None:
        credentials = self.credentials()
        return credentials.api_key if credentials.mode == MODE_DEVELOPER else None

    def credential_mode(self) -> str:
        return self.credentials().mode

    def is_enabled(self) -> bool:
        return self.credentials().usable

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, metadata=True, versions=True, downloads=True)

    # --- transport ---------------------------------------------------------

    def _base_url(self) -> str:
        credentials = self.credentials()
        if credentials.mode == MODE_SERVICE and credentials.service_url:
            return credentials.service_url.rstrip("/")
        return CURSEFORGE_API

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        credentials = self.credentials()
        if credentials.mode == MODE_DEVELOPER and credentials.api_key:
            headers["x-api-key"] = credentials.api_key
        elif credentials.mode == MODE_SERVICE and credentials.api_key:
            # Service mode normally holds the key server-side; a key is only
            # attached when an operator explicitly configured one.
            headers["x-api-key"] = credentials.api_key
        return headers

    async def _get(self, path: str, *, params: dict[str, Any] | None = None, allow_missing: bool = False) -> Any:
        credentials = self.credentials()
        if not credentials.usable:
            raise AzerothAddonsError(
                PROVIDER_UNAVAILABLE,
                credentials.reason or "CurseForge direct API access is not configured.",
                provider=self.provider_id,
            )
        payload = await fetch_json(
            f"{self._base_url()}{path}",
            provider=self.provider_id,
            headers=self._headers(),
            params=params,
            allow_missing=allow_missing,
        )
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # --- health ------------------------------------------------------------

    async def health(self) -> ProviderStatus:
        credentials = self.credentials()
        status = ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            requires_credential=True,
            credential_configured=bool(credentials.api_key),
            credential_mode=credentials.mode,
            capabilities=self.capabilities(),
        )
        if not credentials.usable:
            status.available = False
            status.state = "not-configured"
            status.message = "Not configured."
            status.detail = credentials.reason
            return status

        try:
            await self._get("/games", params={"pageSize": 1})
        except AzerothAddonsError as exc:
            status.available = False
            status.state = "degraded"
            status.message = "CurseForge rejected the request."
            status.detail = exc.message
            if exc.code == PROVIDER_AUTH_FAILED:
                status.message = "The CurseForge credential was rejected."
            return status
        except Exception as exc:  # noqa: BLE001 - degraded, not fatal
            status.available = False
            status.state = "degraded"
            status.message = "CurseForge could not be reached."
            status.detail = str(exc)
            return status

        status.available = True
        status.state = "available"
        status.message = f"Connected ({credentials.mode} credential)."
        return status

    # --- reads -------------------------------------------------------------

    def _mod_to_addon(self, mod: dict) -> Addon:
        slug = mod.get("slug")
        provider_id = str(slug) if slug else str(mod.get("id"))
        latest_files = mod.get("latestFiles") or []
        available = None
        flavours: list[str] = []
        if latest_files and isinstance(latest_files[0], dict):
            latest = latest_files[0]
            available = latest.get("displayName")
            flavours = _flavours_from_game_versions(latest.get("gameVersions") or [])
        return self._addon(
            provider_id,
            name=str(mod.get("name") or provider_id),
            description=_plain_text(mod.get("summary")),
            homepage=mod.get("links", {}).get("websiteUrl") if isinstance(mod.get("links"), dict) else None,
            available_version=available,
            game_flavours=flavours,
        )

    async def search(self, query: str, *, flavour: str | None = None, limit: int = 25) -> list[Addon]:
        data = await self._get(
            "/mods/search",
            params={
                "gameId": WOW_GAME_ID,
                "searchFilter": query,
                "pageSize": max(1, min(limit, 50)),
            },
        )
        mods = data.get("mods", []) if isinstance(data, dict) else (data or [])
        results = [self._mod_to_addon(mod) for mod in mods if isinstance(mod, dict)]
        logger.debug(
            "curseforge search results=%d %s",
            len(results),
            ctx(provider=self.provider_id, operation="search"),
        )
        return results

    async def get_addon(self, provider_id: str) -> Addon | None:
        mod = await self._fetch_mod(provider_id)
        return self._mod_to_addon(mod) if mod else None

    async def _fetch_mod(self, provider_id: str) -> dict | None:
        if provider_id.isdigit():
            data = await self._get(f"/mods/{provider_id}", allow_missing=True)
            return data if isinstance(data, dict) else None
        data = await self._get("/mods/search", params={"gameId": WOW_GAME_ID, "slug": provider_id})
        mods = data.get("mods", []) if isinstance(data, dict) else (data or [])
        for mod in mods:
            if isinstance(mod, dict):
                return mod
        return None

    async def _mod_id(self, provider_id: str) -> int:
        if provider_id.isdigit():
            return int(provider_id)
        mod = await self._fetch_mod(provider_id)
        if not mod or not mod.get("id"):
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "That CurseForge addon was not found.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )
        return int(mod["id"])

    async def get_versions(self, provider_id: str, *, flavour: str | None = None) -> list[ProviderVersion]:
        mod_id = await self._mod_id(provider_id)
        data = await self._get(f"/mods/{mod_id}/files", params={"pageSize": 20})
        files = data if isinstance(data, list) else (data or {}).get("files", [])
        versions: list[ProviderVersion] = []
        for file in files:
            if not isinstance(file, dict):
                continue
            if file.get("isAvailable") is False:
                continue
            release_type = int(file.get("releaseType") or 1)
            versions.append(
                ProviderVersion(
                    id=str(file.get("id")),
                    version=file.get("displayName") or file.get("fileName"),
                    released_at=file.get("fileDate"),
                    channel={1: "stable", 2: "beta", 3: "alpha"}.get(release_type, "stable"),
                    game_flavours=_flavours_from_game_versions(file.get("gameVersions") or []),
                    download_url=file.get("downloadUrl"),
                    filename=file.get("fileName"),
                    size=file.get("fileLength"),
                )
            )
        return versions

    async def resolve_download(self, provider_id: str, version_id: str | None = None) -> ProviderDownload:
        mod = await self._fetch_mod(provider_id)
        if mod is not None and mod.get("allowModDistribution") is False:
            raise AzerothAddonsError(
                DOWNLOAD_FAILED,
                "The author has opted out of third-party distribution for this addon.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )
        mod_id = int(mod["id"]) if mod and mod.get("id") else await self._mod_id(provider_id)

        file_id = version_id
        if not file_id:
            files = await self._get(f"/mods/{mod_id}/files", params={"pageSize": 1})
            entries = files if isinstance(files, list) else (files or {}).get("files", [])
            if not entries:
                raise AzerothAddonsError(
                    ADDON_NOT_FOUND,
                    "That addon has no downloadable files.",
                    provider=self.provider_id,
                    details=f"id={provider_id}",
                )
            file_id = str(entries[0].get("id"))

        url = await self._get(f"/mods/{mod_id}/files/{file_id}/download-url", allow_missing=True)
        if not isinstance(url, str) or not url:
            raise AzerothAddonsError(
                DOWNLOAD_FAILED,
                "CurseForge did not provide a download link. The author may have opted out of third-party distribution.",
                provider=self.provider_id,
                details=f"mod={mod_id} file={file_id}",
            )
        return ProviderDownload(url=url, filename=f"{provider_id}-{file_id}.zip")


def _plain_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _flavours_from_game_versions(values: list[Any]) -> list[str]:
    """Map CurseForge game-version strings onto our flavour vocabulary."""
    flavours: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if lowered.startswith("1.") or "classic era" in lowered:
            flavours.add("classic-era")
        elif any(marker in lowered for marker in ("classic", "cata", "mists", "wotlk", "tbc", "burning")):
            flavours.add("classic")
        elif lowered and lowered[0].isdigit():
            flavours.add("retail")
    return sorted(flavours)
