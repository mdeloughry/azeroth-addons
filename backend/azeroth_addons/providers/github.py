"""GitHub addon provider.

Uses the documented releases API and treats releases strictly as untrusted
downloadable data - Azeroth Addons never clones a repository or executes a
build script.

Identifiers stay provider-neutral on the surface (``provider=github``) while the
underlying GitHub identifier is the conventional ``owner/repository``.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Callable, Sequence

from ..addons.models import PROVIDER_GITHUB, Addon
from ..errors import ADDON_NOT_FOUND, AzerothAddonsError
from ..logctx import ctx, get_logger
from .base import AddonProvider
from .http import fetch_json
from .models import ProviderCapabilities, ProviderDownload, ProviderStatus, ProviderVersion

logger = get_logger()

GITHUB_API = "https://api.github.com"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ZIP_TYPES = ("application/zip", "application/x-zip-compressed", "application/octet-stream")

# Filename suffixes used by the WoW addon community to mark game versions.
_FLAVOUR_SUFFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("classic-era", ("-classic", "-vanilla", "-era", "-sod")),
    ("classic", ("-cata", "-mists", "-mop", "-wrath", "-wotlkc", "-tbc", "-bcc", "-bc", "-titan")),
    ("retail", ("-mainline", "-retail", "-live")),
)


def flavour_from_filename(filename: str) -> str:
    lowered = filename.lower()
    for flavour, suffixes in _FLAVOUR_SUFFIXES:
        if any(suffix in lowered for suffix in suffixes):
            return flavour
    return "retail"


def _is_zip_asset(asset: dict) -> bool:
    name = str(asset.get("name") or "")
    if not name.lower().endswith(".zip"):
        return False
    content_type = str(asset.get("content_type") or "")
    return content_type in ZIP_TYPES or content_type == ""


def _is_nolib(asset: dict) -> bool:
    return "nolib" in str(asset.get("name") or "").lower()


class GitHubProvider(AddonProvider):
    provider_id = PROVIDER_GITHUB
    display_name = "GitHub"
    requires_credential = False
    credential_key = "github"

    def __init__(self, credential_provider: Callable[[], str | None] | None = None) -> None:
        self._credential_provider = credential_provider
        self._rate_limit: dict[str, str] = {}
        self._search_release_cache: dict[str, tuple[float, bool]] = {}
        self._release_checks = asyncio.Semaphore(3)

    # --- credentials / capabilities ---------------------------------------

    def credential(self) -> str | None:
        if self._credential_provider is None:
            return None
        return self._credential_provider() or None

    def credential_mode(self) -> str:
        return "authenticated" if self.credential() else "anonymous"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, metadata=True, versions=True, downloads=True)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = self.credential()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # --- health ------------------------------------------------------------

    async def health(self) -> ProviderStatus:
        status = ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            requires_credential=False,
            credential_configured=bool(self.credential()),
            credential_mode=self.credential_mode(),
            capabilities=self.capabilities(),
            available=True,
            state="available",
        )
        try:
            payload = await fetch_json(
                f"{GITHUB_API}/rate_limit",
                provider=self.provider_id,
                headers=self._headers(),
                timeout=8.0,
                allow_missing=True,
            )
        except Exception as exc:  # noqa: BLE001 - degraded, not fatal
            status.available = False
            status.state = "degraded"
            status.message = "GitHub could not be reached."
            status.detail = getattr(exc, "details", None) or str(exc)
            return status

        core = (payload or {}).get("resources", {}).get("core", {}) if isinstance(payload, dict) else {}
        remaining = core.get("remaining")
        if remaining is not None:
            self._rate_limit = {"remaining": str(remaining), "limit": str(core.get("limit", ""))}
            status.detail = f"rate limit remaining={remaining}"
            if isinstance(remaining, int) and remaining <= 0:
                status.available = False
                status.state = "degraded"
                status.message = "GitHub rate limit exhausted. Add a personal access token to raise it."
        return status

    # --- reads -------------------------------------------------------------

    async def search(self, query: str, *, flavour: str | None = None, limit: int = 25) -> list[Addon]:
        payload = await fetch_json(
            f"{GITHUB_API}/search/repositories",
            provider=self.provider_id,
            headers=self._headers(),
            params={
                "q": f"{query} wow addon in:name,description",
                "sort": "stars",
                "order": "desc",
                "per_page": max(1, min(limit, 10)),
            },
            timeout=12.0,
        )
        items = payload.get("items", []) if isinstance(payload, dict) else []
        results: list[Addon] = []
        candidates: list[dict] = []
        for repo in items:
            if not isinstance(repo, dict) or repo.get("archived") or repo.get("fork"):
                continue
            full_name = str(repo.get("full_name") or "")
            if not REPO_PATTERN.match(full_name):
                continue
            candidates.append(repo)

        async def has_addon_release(repo: dict) -> bool:
            full_name = repo["full_name"]
            cached = self._search_release_cache.get(full_name.lower())
            if cached and time.monotonic() - cached[0] < 300:
                return cached[1]
            async with self._release_checks:
                releases = await self._releases(full_name, limit=5)
                usable = any(not release.get("draft") and self._assets_for(release) for release in releases)
                self._search_release_cache[full_name.lower()] = (time.monotonic(), usable)
                return usable

        checks = await asyncio.gather(*(has_addon_release(repo) for repo in candidates), return_exceptions=True)
        errors = []
        for repo, usable in zip(candidates, checks):
            if isinstance(usable, BaseException):
                errors.append(usable)
                continue
            if not usable:
                continue
            full_name = repo["full_name"]
            results.append(
                self._addon(
                    full_name,
                    name=str(repo.get("name") or full_name),
                    description=repo.get("description"),
                    homepage=repo.get("html_url"),
                )
            )
        if errors and not results:
            raise errors[0]
        logger.debug(
            "github search results=%d %s",
            len(results),
            ctx(provider=self.provider_id, operation="search"),
        )
        return results

    async def get_addon(self, provider_id: str) -> Addon | None:
        self._require_repo(provider_id)
        repo = await fetch_json(
            f"{GITHUB_API}/repos/{provider_id}",
            provider=self.provider_id,
            headers=self._headers(),
            allow_missing=True,
        )
        if not isinstance(repo, dict):
            return None
        return self._addon(
            provider_id,
            name=str(repo.get("name") or provider_id),
            description=repo.get("description"),
            homepage=repo.get("html_url"),
        )

    def _require_repo(self, provider_id: str) -> None:
        if not REPO_PATTERN.match(provider_id):
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "GitHub addons are identified as owner/repository.",
                provider=self.provider_id,
                details=f"id={provider_id}",
            )

    async def _releases(self, provider_id: str, limit: int = 20) -> list[dict]:
        self._require_repo(provider_id)
        payload = await fetch_json(
            f"{GITHUB_API}/repos/{provider_id}/releases",
            provider=self.provider_id,
            headers=self._headers(),
            params={"per_page": max(1, min(limit, 100))},
            timeout=12.0,
            allow_missing=True,
        )
        if not isinstance(payload, list):
            return []
        return [release for release in payload if isinstance(release, dict)]

    @staticmethod
    def _assets_for(release: dict) -> list[dict]:
        assets = release.get("assets") or []
        zips = [asset for asset in assets if isinstance(asset, dict) and _is_zip_asset(asset)]
        preferred = [asset for asset in zips if not _is_nolib(asset)]
        return preferred or zips

    @staticmethod
    def _pick_asset(assets: Sequence[dict], flavour: str | None) -> dict:
        if flavour:
            for asset in assets:
                if flavour_from_filename(str(asset.get("name") or "")) == flavour:
                    return asset
        return assets[0]

    async def get_versions(self, provider_id: str, *, flavour: str | None = None) -> list[ProviderVersion]:
        versions: list[ProviderVersion] = []
        for release in await self._releases(provider_id):
            if release.get("draft"):
                continue
            assets = self._assets_for(release)
            if not assets:
                continue
            best = self._pick_asset(assets, flavour)
            filename = str(best.get("name") or "")
            versions.append(
                ProviderVersion(
                    id=str(release.get("tag_name") or release.get("id") or ""),
                    version=str(release.get("tag_name") or ""),
                    released_at=release.get("published_at"),
                    channel="prerelease" if release.get("prerelease") else "stable",
                    game_flavours=[flavour_from_filename(filename)],
                    download_url=best.get("browser_download_url"),
                    filename=filename,
                    size=best.get("size"),
                )
            )
        return versions

    async def resolve_download(self, provider_id: str, version_id: str | None = None) -> ProviderDownload:
        release: dict | None
        if version_id:
            release = await fetch_json(
                f"{GITHUB_API}/repos/{provider_id}/releases/tags/{version_id}",
                provider=self.provider_id,
                headers=self._headers(),
                allow_missing=True,
            )
        else:
            releases = await self._releases(provider_id, limit=1)
            release = releases[0] if releases else None

        if not isinstance(release, dict):
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "No downloadable release was found for that addon.",
                provider=self.provider_id,
                details=f"repo={provider_id} version={version_id}",
            )

        assets = self._assets_for(release)
        if not assets:
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "That release does not contain an addon archive.",
                provider=self.provider_id,
                details=f"repo={provider_id} tag={release.get('tag_name')}",
            )
        asset = self._pick_asset(assets, None)
        return ProviderDownload(
            url=str(asset.get("browser_download_url") or ""),
            filename=str(asset.get("name") or ""),
            size=asset.get("size"),
        )
