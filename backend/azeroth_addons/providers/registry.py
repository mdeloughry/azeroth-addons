"""Provider registry.

Adding a provider is one registration call. Nothing in the application
branches on ``provider == "curseforge"``: capability discovery answers the
question instead.
"""

from __future__ import annotations

from typing import Iterator

from ..errors import PROVIDER_UNAVAILABLE, AzerothAddonsError
from ..logctx import get_logger
from .base import AddonProvider
from .models import ProviderStatus

logger = get_logger()


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AddonProvider] = {}

    def register(self, provider: AddonProvider) -> None:
        self._providers[provider.provider_id] = provider
        logger.info("registered provider %s", provider.provider_id)

    def get(self, provider_id: str) -> AddonProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise AzerothAddonsError(
                PROVIDER_UNAVAILABLE,
                f"The '{provider_id}' addon source is not available.",
                provider=provider_id,
                details=f"known={sorted(self._providers)}",
            )
        return provider

    def get_or_none(self, provider_id: str) -> AddonProvider | None:
        return self._providers.get(provider_id)

    def ids(self) -> list[str]:
        return sorted(self._providers)

    def all(self) -> list[AddonProvider]:
        return [self._providers[key] for key in self.ids()]

    def enabled(self) -> list[AddonProvider]:
        return [provider for provider in self.all() if provider.is_enabled()]

    def __iter__(self) -> Iterator[AddonProvider]:
        return iter(self.all())

    async def statuses(self) -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []
        for provider in self.all():
            try:
                statuses.append(await provider.health())
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                logger.error("provider %s health check failed: %s", provider.provider_id, exc)
                statuses.append(
                    ProviderStatus(
                        provider_id=provider.provider_id,
                        display_name=provider.display_name,
                        available=False,
                        state="degraded",
                        message="The addon source reported an error.",
                        detail=str(exc),
                        capabilities=provider.capabilities(),
                    )
                )
        return statuses
