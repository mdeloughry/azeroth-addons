"""Provider wiring.

Everything that depends on runtime configuration (credentials, feature flags)
is resolved through callables, so a credential change takes effect without
rebuilding the registry.
"""

from __future__ import annotations

from ..settings import SettingsStore
from .curseforge import CurseForgeProvider
from .github import GitHubProvider
from .registry import ProviderRegistry
from .tukui import TukUIProvider
from .wago import WagoProvider
from .wowinterface import WowInterfaceProvider

# Feature flag: direct CurseForge API support ships disabled. Enabling it is a
# deliberate, documented step that requires an approved credential.
FEATURE_DIRECT_CURSEFORGE = "enableDirectCurseForge"


def build_registry(settings: SettingsStore, target: ProviderRegistry) -> ProviderRegistry:
    """Register every provider into ``target`` (required: no shared global)."""

    target.register(GitHubProvider(credential_provider=lambda: settings.credential("github")))
    target.register(TukUIProvider())
    target.register(
        CurseForgeProvider(
            credential_provider=lambda: settings.credential("curseforge"),
            feature_enabled=lambda: bool(settings.get(FEATURE_DIRECT_CURSEFORGE, False)),
            service_url_provider=lambda: settings.get("curseForgeServiceUrl"),
        )
    )
    # Registered but disabled: keeps status/UI honest without pretending a
    # sanctioned integration exists.
    target.register(WagoProvider())
    target.register(WowInterfaceProvider())
    return target
