from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from azeroth_addons import providers
from azeroth_addons.addons.models import Addon
from azeroth_addons.errors import (
    ADDON_NOT_FOUND,
    DOWNLOAD_FAILED,
    NETWORK_ERROR,
    PROVIDER_AUTH_FAILED,
    PROVIDER_BAD_RESPONSE,
    PROVIDER_RATE_LIMITED,
    PROVIDER_UNAVAILABLE,
    AzerothAddonsError,
)
from azeroth_addons.providers import http as http_module
from azeroth_addons.providers.base import AddonProvider
from azeroth_addons.providers.curseforge import MODE_DISABLED, MODE_DEVELOPER, CurseForgeProvider
from azeroth_addons.providers.github import GitHubProvider, flavour_from_filename
from azeroth_addons.providers.models import ProviderCapabilities
from azeroth_addons.providers.registry import ProviderRegistry
from azeroth_addons.providers.tukui import TukUIProvider
from azeroth_addons.providers.wago import WagoProvider
from azeroth_addons.providers.wowinterface import WowInterfaceProvider
from azeroth_addons.settings import JsonStore, SettingsStore


def make_settings(tmp_path: Path, **values) -> SettingsStore:
    store = JsonStore(tmp_path / "settings")
    settings = SettingsStore(store)
    settings.load()
    if values:
        settings.update(values)
    return settings


# --- registry --------------------------------------------------------------


def test_provider_registry_registers_and_reports_capabilities():
    registry = ProviderRegistry()
    registry.register(TukUIProvider())
    assert registry.ids() == ["tukui"]
    assert registry.get("tukui").provider_id == "tukui"
    assert registry.get_or_none("missing") is None
    assert registry.all()[0].capabilities().versions is True


def test_provider_registry_unknown_provider_raises():
    registry = ProviderRegistry()
    with pytest.raises(AzerothAddonsError) as excinfo:
        registry.get("nope")
    assert excinfo.value.code == PROVIDER_UNAVAILABLE


async def test_provider_registry_statuses_isolate_failures():
    class Exploding(AddonProvider):
        provider_id = "boom"
        display_name = "Boom"

        async def health(self):
            raise RuntimeError("kaput")

    registry = ProviderRegistry()
    registry.register(TukUIProvider())
    registry.register(Exploding())
    statuses = {status.provider_id: status for status in await registry.statuses()}
    assert statuses["boom"].state == "degraded"
    assert statuses["tukui"].available in (True, False)


def test_capabilities_to_dict():
    caps = ProviderCapabilities(search=True, metadata=True, versions=False, downloads=True)
    assert caps.to_dict() == {
        "search": True,
        "metadata": True,
        "versions": False,
        "downloads": True,
    }


def test_provider_factory_registers_every_source(tmp_path: Path):
    from azeroth_addons.providers.factory import build_registry

    registry = ProviderRegistry()
    build_registry(make_settings(tmp_path), registry)
    assert registry.ids() == ["curseforge", "github", "tukui", "wago", "wowinterface"]
    enabled = {provider.provider_id for provider in registry.enabled()}
    # Keyless sources work out of the box; direct CurseForge does not.
    assert "github" in enabled and "tukui" in enabled
    assert "curseforge" not in enabled
    assert "wago" not in enabled and "wowinterface" not in enabled


# --- http error mapping ----------------------------------------------------


def _http_error(code: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.test/x", code, "error", headers or {}, None)


async def test_http_maps_auth_failure(monkeypatch):
    def fake(url, **kwargs):
        raise _http_error(401)

    monkeypatch.setattr(http_module, "_perform", fake)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x", provider="github")
    assert excinfo.value.code == PROVIDER_AUTH_FAILED
    assert excinfo.value.provider == "github"


async def test_http_maps_exhausted_rate_limit(monkeypatch):
    def fake(url, **kwargs):
        raise _http_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "999"})

    monkeypatch.setattr(http_module, "_perform", fake)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == PROVIDER_RATE_LIMITED


async def test_http_maps_too_many_requests(monkeypatch):
    def fake(url, **kwargs):
        raise _http_error(429, {"retry-after": "60"})

    monkeypatch.setattr(http_module, "_perform", fake)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == PROVIDER_RATE_LIMITED
    assert "retry_after=60" in (excinfo.value.details or "")


async def test_http_allow_missing_returns_none_for_404(monkeypatch):
    def fake(url, **kwargs):
        raise _http_error(404)

    monkeypatch.setattr(http_module, "_perform", fake)
    assert await http_module.fetch_json("https://example.test/x", allow_missing=True) is None
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == ADDON_NOT_FOUND


async def test_http_maps_server_error_and_network_failure(monkeypatch):
    def server_error(url, **kwargs):
        raise _http_error(503)

    monkeypatch.setattr(http_module, "_perform", server_error)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == PROVIDER_UNAVAILABLE

    def offline(url, **kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(http_module, "_perform", offline)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == NETWORK_ERROR


async def test_http_maps_bad_json(monkeypatch):
    def fake(url, **kwargs):
        return 200, {}, b"<html>not json</html>"

    monkeypatch.setattr(http_module, "_perform", fake)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await http_module.fetch_json("https://example.test/x")
    assert excinfo.value.code == PROVIDER_BAD_RESPONSE


def test_build_url_appends_params():
    assert http_module.build_url("https://x.test/a", {"q": "hello world", "n": None}) == (
        "https://x.test/a?q=hello+world"
    )
    assert http_module.build_url("https://x.test/a?x=1", {"y": "2"}) == "https://x.test/a?x=1&y=2"


# --- github ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "flavour"),
    [
        ("MyAddon-1.0.zip", "retail"),
        ("MyAddon-classic-1.0.zip", "classic-era"),
        ("MyAddon-vanilla.zip", "classic-era"),
        ("MyAddon-cata.zip", "classic"),
        ("MyAddon-mists-2.0.zip", "classic"),
        ("MyAddon-mainline.zip", "retail"),
    ],
)
def test_github_flavour_from_filename(filename, flavour):
    assert flavour_from_filename(filename) == flavour


async def test_github_search_filters_forks_and_archived(monkeypatch):
    payload = {
        "items": [
            {"full_name": "SFX-WoW/Masque", "name": "Masque", "description": "Skinning", "html_url": "u1"},
            {"full_name": "someone/forked", "name": "forked", "fork": True},
            {"full_name": "someone/old", "name": "old", "archived": True},
            {"full_name": "bad name", "name": "bad"},
        ]
    }

    async def fake_fetch(url, **kwargs):
        return payload

    monkeypatch.setattr("azeroth_addons.providers.github.fetch_json", fake_fetch)
    results = await GitHubProvider().search("masque")
    assert [(addon.provider, addon.provider_id) for addon in results] == [("github", "SFX-WoW/Masque")]


async def test_github_get_addon_and_versions(monkeypatch):
    def handler(url, **kwargs):
        if url.endswith("/repos/SFX-WoW/Masque"):
            return {
                "full_name": "SFX-WoW/Masque",
                "name": "Masque",
                "description": "Skinning",
                "html_url": "https://github.com/SFX-WoW/Masque",
            }
        if "/releases" in url:
            return [
                {
                    "tag_name": "v2.0.0",
                    "published_at": "2026-01-02T00:00:00Z",
                    "prerelease": False,
                    "assets": [
                        {
                            "name": "Masque-nolib.zip",
                            "content_type": "application/zip",
                            "browser_download_url": "nolib",
                            "size": 10,
                        },
                        {
                            "name": "Masque-classic.zip",
                            "content_type": "application/zip",
                            "browser_download_url": "classic-url",
                            "size": 20,
                        },
                    ],
                },
                {"tag_name": "v1.9.0", "draft": True, "assets": []},
            ]
        return None

    async def fake_fetch(url, **kwargs):
        return handler(url, **kwargs)

    monkeypatch.setattr("azeroth_addons.providers.github.fetch_json", fake_fetch)
    provider = GitHubProvider()
    addon = await provider.get_addon("SFX-WoW/Masque")
    assert addon is not None and addon.name == "Masque"

    versions = await provider.get_versions("SFX-WoW/Masque")
    assert len(versions) == 1  # drafts are skipped
    assert versions[0].version == "v2.0.0"
    assert versions[0].filename == "Masque-classic.zip"  # nolib asset is skipped
    assert versions[0].game_flavours == ["classic-era"]


async def test_github_get_addon_rejects_bad_identifiers(monkeypatch):
    with pytest.raises(AzerothAddonsError) as excinfo:
        await GitHubProvider().get_addon("not-a-repo")
    assert excinfo.value.code == ADDON_NOT_FOUND


async def test_github_health_reports_exhausted_rate_limit(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return {"resources": {"core": {"remaining": 0, "limit": 60}}}

    monkeypatch.setattr("azeroth_addons.providers.github.fetch_json", fake_fetch)
    status = await GitHubProvider().health()
    assert status.available is False
    assert status.state == "degraded"


async def test_github_health_is_available_with_headroom(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return {"resources": {"core": {"remaining": 55, "limit": 60}}}

    monkeypatch.setattr("azeroth_addons.providers.github.fetch_json", fake_fetch)
    status = await GitHubProvider().health()
    assert status.available is True
    assert status.credential_mode == "anonymous"


# --- tukui -----------------------------------------------------------------


async def test_tukui_versions_and_download(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return {"version": "15.26", "patch": ["retail"], "url": "https://api.tukui.org/v1/download/elvui/tok"}

    monkeypatch.setattr("azeroth_addons.providers.tukui.fetch_json", fake_fetch)
    provider = TukUIProvider()
    versions = await provider.get_versions("elvui")
    assert versions[0].version == "15.26"
    assert versions[0].download_url.endswith("/tok")
    download = await provider.resolve_download("elvui")
    assert download.filename == "elvui.zip"


async def test_tukui_rejects_unknown_projects():
    with pytest.raises(AzerothAddonsError) as excinfo:
        await TukUIProvider().get_addon("some-other-addon")
    assert excinfo.value.code == ADDON_NOT_FOUND


# --- curseforge ------------------------------------------------------------


def test_curseforge_is_disabled_without_a_flag(tmp_path: Path):
    provider = CurseForgeProvider(
        credential_provider=lambda: "some-key",
        feature_enabled=lambda: False,
    )
    assert provider.is_enabled() is False
    assert provider.credentials().mode == MODE_DISABLED
    assert provider.credentials().reason and "disabled" in provider.credentials().reason.lower()


def test_curseforge_is_enabled_with_flag_and_credential(tmp_path: Path):
    provider = CurseForgeProvider(
        credential_provider=lambda: "some-key",
        feature_enabled=lambda: True,
    )
    assert provider.is_enabled() is True
    credentials = provider.credentials()
    assert credentials.mode == MODE_DEVELOPER
    assert provider.capabilities().search is True


async def test_curseforge_health_when_disabled(tmp_path: Path):
    provider = CurseForgeProvider(credential_provider=lambda: None, feature_enabled=lambda: False)
    status = await provider.health()
    assert status.available is False
    assert status.state == "not-configured"
    assert status.message == "Not configured."


async def test_curseforge_search_raises_when_disabled():
    provider = CurseForgeProvider(credential_provider=lambda: None, feature_enabled=lambda: True)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await provider.search("masque")
    assert excinfo.value.code == PROVIDER_UNAVAILABLE


async def test_curseforge_search_maps_mods(monkeypatch, tmp_path: Path):
    payload = {
        "data": {
            "mods": [
                {
                    "id": 12345,
                    "slug": "masque",
                    "name": "Masque",
                    "summary": "Skinning",
                    "allowModDistribution": True,
                    "links": {"websiteUrl": "https://www.curseforge.com/wow/addons/masque"},
                    "latestFiles": [
                        {"displayName": "2.0.0", "gameVersions": ["11.1.7", "1.15.7"]}
                    ],
                }
            ]
        }
    }

    async def fake_fetch(url, **kwargs):
        return payload

    monkeypatch.setattr("azeroth_addons.providers.curseforge.fetch_json", fake_fetch)
    provider = CurseForgeProvider(credential_provider=lambda: "key", feature_enabled=lambda: True)
    results = await provider.search("masque")
    assert results[0].provider_id == "masque"
    assert results[0].homepage.endswith("/masque")
    assert results[0].available_version == "2.0.0"
    assert set(results[0].game_flavours) == {"retail", "classic-era"}


async def test_curseforge_respects_author_opt_out(monkeypatch):
    async def fake_fetch(url, **kwargs):
        # Slug lookups go through the search endpoint.
        return {"data": {"mods": [{"id": 99, "slug": "opted-out", "allowModDistribution": False}]}}

    monkeypatch.setattr("azeroth_addons.providers.curseforge.fetch_json", fake_fetch)
    provider = CurseForgeProvider(credential_provider=lambda: "key", feature_enabled=lambda: True)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await provider.resolve_download("opted-out")
    assert excinfo.value.code == DOWNLOAD_FAILED
    assert "opted out" in excinfo.value.message


async def test_curseforge_health_reports_rejected_credential(monkeypatch):
    async def fake_fetch(url, **kwargs):
        raise AzerothAddonsError(PROVIDER_AUTH_FAILED, "rejected")

    monkeypatch.setattr("azeroth_addons.providers.curseforge.fetch_json", fake_fetch)
    provider = CurseForgeProvider(credential_provider=lambda: "bad-key", feature_enabled=lambda: True)
    status = await provider.health()
    assert status.available is False
    assert status.message == "The CurseForge credential was rejected."


# --- placeholders ----------------------------------------------------------


@pytest.mark.parametrize("provider_cls", [WagoProvider, WowInterfaceProvider])
async def test_placeholder_providers_are_honest(provider_cls):
    provider = provider_cls()
    status = await provider.health()
    # Deliberately *not* "unavailable": installs from these sources work through
    # the bundled engine, so a failure state would mislead the user.
    assert status.state == "engine-backed"
    assert status.available is False  # cannot serve search or metadata directly
    assert status.message
    assert status.detail  # explains why, without a wall of prose
    capabilities = provider.capabilities()
    assert not any([capabilities.search, capabilities.metadata, capabilities.versions, capabilities.downloads])
