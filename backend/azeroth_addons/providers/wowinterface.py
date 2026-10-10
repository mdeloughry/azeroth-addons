"""WoWInterface provider - placeholder.

WoWInterface's only API is author-side (upload/update). There is no public
catalogue/search/download API for addon managers, so a first-class provider
cannot be built on sanctioned ground.

Installs still work for Retail addons through the bundled engine's ``wowi:``
source. This provider exists to keep the registry and status UI honest.
"""

from __future__ import annotations

from ..addons.models import PROVIDER_WOWINTERFACE, Addon
from ..logctx import get_logger
from .base import AddonProvider
from .models import ProviderCapabilities, ProviderStatus

logger = get_logger()


class WowInterfaceProvider(AddonProvider):
    provider_id = PROVIDER_WOWINTERFACE
    display_name = "WoWInterface"
    requires_credential = False
    credential_key = "wowinterface"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=False, metadata=False, versions=False, downloads=False)

    def is_enabled(self) -> bool:
        return False

    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            available=False,
            state="unavailable",
            requires_credential=False,
            credential_configured=False,
            credential_mode="disabled",
            capabilities=self.capabilities(),
            message="Handled by the bundled engine.",
            detail=(
                "WoWInterface does not publish a catalogue API for addon managers. "
                "Retail addons install through the bundled engine using wowi: identifiers."
            ),
        )

    async def get_addon(self, provider_id: str) -> Addon | None:
        raise self.not_supported("direct WoWInterface lookups")
