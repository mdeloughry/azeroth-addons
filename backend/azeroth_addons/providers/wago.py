"""Wago addon provider - placeholder for a future, sanctioned integration.

Wago's documented API is thin (a public ``/api/data/game`` endpoint plus
author-side upload). The read API used by at least one other manager is
undocumented and effectively partner-only, and Azeroth Addons does not scrape
HTML sites when a supported integration may exist.

For the MVP, Wago is reached through the bundled engine (which supports
``wago:`` identifiers for users who hold a Wago access token). This provider
exists so the registry, capability discovery and status UI are already correct
when a stable integration becomes available.
"""

from __future__ import annotations

from ..addons.models import PROVIDER_WAGO, Addon
from ..logctx import get_logger
from .base import AddonProvider
from .models import ProviderCapabilities, ProviderStatus

logger = get_logger()

WAGO_DATA_API = "https://addons.wago.io/api/data/game"


class WagoProvider(AddonProvider):
    provider_id = PROVIDER_WAGO
    display_name = "Wago"
    requires_credential = True
    credential_key = "wago"

    def capabilities(self) -> ProviderCapabilities:
        # No sanctioned search/metadata/version/download API for third parties.
        return ProviderCapabilities(search=False, metadata=False, versions=False, downloads=False)

    def is_enabled(self) -> bool:
        return False

    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            available=False,
            # Not "unavailable": installs work through the bundled engine.
            state="engine-backed",
            requires_credential=True,
            credential_configured=False,
            credential_mode="disabled",
            capabilities=self.capabilities(),
            message="Installs via the bundled engine.",
            detail=(
                "Wago has no entries in the public addon catalogue. "
                "Downloads require a Wago token and a known wago: identifier."
            ),
        )

    async def get_addon(self, provider_id: str) -> Addon | None:
        raise self.not_supported("direct Wago lookups")
