"""Addon search across every compatible source.

Design goals:

* query the engine and every enabled provider concurrently;
* **a single failing source must not fail the search** - other sources still
  return results, and the failure is reported alongside them;
* results carry their provider so the UI can group and label them;
* deduplication happens only on an exact ``provider:provider_id`` match, never
  on a guessed name match.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence

from ..engines.registry import EngineRegistry
from ..errors import AzerothAddonsError, SEARCH_FAILED
from ..installations.manager import InstallationManager
from ..logctx import ctx, get_logger
from ..providers.base import AddonProvider
from ..providers.registry import ProviderRegistry
from .models import Addon

logger = get_logger()

InstalledProvider = Callable[[str], Awaitable[list[Addon]]]


class AddonSearchService:
    def __init__(
        self,
        installations: InstallationManager,
        engines: EngineRegistry,
        providers: ProviderRegistry,
        installed_provider: InstalledProvider,
    ) -> None:
        self._installations = installations
        self._engines = engines
        self._providers = providers
        self._installed_provider = installed_provider

    async def search(
        self,
        installation_id: str,
        query: str,
        *,
        limit: int = 25,
        provider_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        clean = (query or "").strip()
        installation = self._installations.require_available(installation_id)
        if not clean:
            return {
                "installationId": installation.id,
                "query": "",
                "results": [],
                "failures": [],
                "sources": [],
            }

        jobs: list[tuple[str, Awaitable[list[Addon]]]] = []

        engine = self._engines.get_or_none()
        if engine is not None and engine.capabilities().search:
            status = await engine.status()
            if status.available:
                jobs.append((engine.engine_id, engine.search(installation, clean, limit=limit)))

        for provider in self._searchable_providers(provider_ids):
            jobs.append((provider.provider_id, provider.search(clean, flavour=installation.flavour, limit=limit)))

        results: list[Addon] = []
        failures: list[dict[str, Any]] = []
        sources: list[str] = []

        if jobs:
            outcomes = await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)
            for (source_id, _), outcome in zip(jobs, outcomes):
                if isinstance(outcome, BaseException):
                    error = (
                        outcome
                        if isinstance(outcome, AzerothAddonsError)
                        else AzerothAddonsError(SEARCH_FAILED, str(outcome), provider=source_id)
                    )
                    failures.append({"source": source_id, "error": error.to_dict()})
                    logger.warning(
                        "search source failed source=%s: %s",
                        source_id,
                        error.message,
                    )
                    continue
                sources.append(source_id)
                results.extend(outcome)

        deduped = self._dedupe(results)
        self._annotate_installed(deduped, await self._safe_installed(installation.id))
        deduped.sort(key=lambda addon: (addon.name.lower(), addon.provider))

        logger.info(
            "search query=%r results=%d sources=%d failures=%d %s",
            clean,
            len(deduped),
            len(sources),
            len(failures),
            ctx(installation=installation.id, operation="search"),
        )
        return {
            "installationId": installation.id,
            "query": clean,
            "flavour": installation.flavour,
            "results": [addon.to_dict() for addon in deduped],
            "failures": failures,
            "sources": sources,
            "truncated": len(deduped) > limit,
        }

    def _searchable_providers(self, provider_ids: Sequence[str] | None) -> list[AddonProvider]:
        providers = self._providers.all()
        if provider_ids:
            wanted = set(provider_ids)
            providers = [provider for provider in providers if provider.provider_id in wanted]
        return [
            provider
            for provider in providers
            if provider.capabilities().search and provider.is_enabled()
        ]

    @staticmethod
    def _dedupe(results: Sequence[Addon]) -> list[Addon]:
        seen: dict[tuple[str, str], Addon] = {}
        for addon in results:
            key = (addon.provider, addon.provider_id.lower())
            existing = seen.get(key)
            if existing is None:
                seen[key] = addon
                continue
            # Merge only same-identity results; prefer the richer description.
            if not existing.description and addon.description:
                existing.description = addon.description
            if not existing.homepage and addon.homepage:
                existing.homepage = addon.homepage
            if not existing.available_version and addon.available_version:
                existing.available_version = addon.available_version
        return list(seen.values())

    async def _safe_installed(self, installation_id: str) -> list[Addon]:
        try:
            return await self._installed_provider(installation_id)
        except AzerothAddonsError as exc:
            logger.debug("could not read installed addons for search: %s", exc.message)
            return []

    @staticmethod
    def _annotate_installed(results: Sequence[Addon], installed: Sequence[Addon]) -> None:
        by_key = {(addon.provider, addon.provider_id.lower()): addon for addon in installed}
        for addon in results:
            match = by_key.get((addon.provider, addon.provider_id.lower()))
            if match is not None:
                addon.installed_version = match.installed_version
                addon.state = match.state
                addon.pinned = match.pinned
