from __future__ import annotations

import pytest
from conftest import FakeEngine

from azeroth_addons.addons.models import PROVIDER_GITHUB, PROVIDER_TUKUI, Addon
from azeroth_addons.errors import PROVIDER_UNAVAILABLE, SEARCH_FAILED, AzerothAddonsError
from azeroth_addons.providers.base import AddonProvider
from azeroth_addons.providers.models import ProviderCapabilities


class StubProvider(AddonProvider):
    def __init__(
        self,
        provider_id: str,
        *,
        results: list[Addon] | None = None,
        error: Exception | None = None,
        searchable: bool = True,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.display_name = provider_id.title()
        self._results = results or []
        self._error = error
        self._capabilities = capabilities or ProviderCapabilities(
            search=searchable, metadata=True, versions=True, downloads=True
        )
        self.queries: list[str] = []

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def search(self, query: str, *, flavour: str | None = None, limit: int = 25) -> list[Addon]:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return list(self._results)


def _addon(provider: str, provider_id: str, *, name: str | None = None) -> Addon:
    return Addon(
        id=f"{provider}:{provider_id}",
        name=name or provider_id,
        provider=provider,
        provider_id=provider_id,
    )


@pytest.fixture
def wired(stack, installation, seed_installation):
    def _wire(*, engine=None, providers=()):
        return stack(
            engine=engine or FakeEngine(),
            providers=list(providers),
            register=lambda manager: seed_installation(manager, installation),
        )

    _wire.installation = installation  # type: ignore[attr-defined]
    return _wire


async def test_search_combines_engine_and_providers(wired) -> None:
    github = StubProvider(PROVIDER_GITHUB, results=[_addon(PROVIDER_GITHUB, "owner/repo", name="Repo Addon")])
    tukui = StubProvider(PROVIDER_TUKUI, results=[_addon(PROVIDER_TUKUI, "elvui", name="ElvUI")])
    registered = wired(
        engine=FakeEngine(search_results=[_addon("curseforge", "details", name="Details!")]),
        providers=[github, tukui],
    )

    payload = await registered.search.search(wired.installation.id, "details")
    assert {result["provider"] for result in payload["results"]} == {"curseforge", "github", "tukui"}
    assert payload["failures"] == []
    assert set(payload["sources"]) == {"fake", PROVIDER_GITHUB, PROVIDER_TUKUI}
    assert github.queries == ["details"]  # the query reaches every provider


async def test_search_survives_a_failing_provider(wired):
    registered = wired(
        engine=FakeEngine(search_results=[_addon("curseforge", "masque")]),
        providers=[
            StubProvider(PROVIDER_GITHUB, error=AzerothAddonsError(PROVIDER_UNAVAILABLE, "github down")),
            StubProvider(PROVIDER_TUKUI, results=[_addon(PROVIDER_TUKUI, "elvui")]),
        ],
    )
    payload = await registered.search.search(wired.installation.id, "masque")
    assert {result["provider"] for result in payload["results"]} == {"curseforge", "tukui"}
    assert payload["failures"][0]["source"] == PROVIDER_GITHUB
    assert payload["failures"][0]["error"]["code"] == PROVIDER_UNAVAILABLE


async def test_search_converts_unexpected_errors(wired):
    registered = wired(providers=[StubProvider(PROVIDER_GITHUB, error=RuntimeError("unexpected"))])
    payload = await registered.search.search(wired.installation.id, "anything")
    assert payload["failures"][0]["error"]["code"] == SEARCH_FAILED


async def test_search_never_merges_across_providers(wired):
    duplicate = _addon("curseforge", "masque")
    duplicate.description = "richer"
    registered = wired(
        engine=FakeEngine(search_results=[_addon("curseforge", "masque")]),
        providers=[StubProvider(PROVIDER_GITHUB, results=[duplicate, _addon("github", "masque")])],
    )
    payload = await registered.search.search(wired.installation.id, "masque")
    keys = [(result["provider"], result["providerId"]) for result in payload["results"]]
    assert len(keys) == len(set(keys))
    assert ("curseforge", "masque") in keys
    assert ("github", "masque") in keys


async def test_search_annotates_installed_addons(wired, addon_factory):
    installed = addon_factory("curseforge", "masque", version="1.2.3")
    registered = wired(
        engine=FakeEngine(
            addons=[installed],
            search_results=[_addon("curseforge", "masque"), _addon("curseforge", "other")],
        )
    )
    payload = await registered.search.search(wired.installation.id, "masque")
    by_id = {result["id"]: result for result in payload["results"]}
    assert by_id["curseforge:masque"]["installedVersion"] == "1.2.3"
    assert "installedVersion" not in by_id["curseforge:other"]


async def test_search_skips_providers_without_search_capability(wired):
    non_searchable = StubProvider(
        "wago",
        results=[_addon("wago", "x")],
        searchable=False,
        capabilities=ProviderCapabilities(search=False),
    )
    registered = wired(providers=[non_searchable])
    payload = await registered.search.search(wired.installation.id, "x")
    assert payload["results"] == []
    assert non_searchable.queries == []


async def test_empty_query_returns_nothing(wired):
    registered = wired()
    payload = await registered.search.search(wired.installation.id, "   ")
    assert payload["results"] == []
    assert payload["query"] == ""
