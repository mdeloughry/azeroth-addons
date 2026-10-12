from __future__ import annotations

import asyncio

import pytest

from azeroth_addons.engines.catalogue import CatalogueSearch
from azeroth_addons.errors import AzerothAddonsError, SEARCH_FAILED


def entry(source="curse", name="Spoken Player", flavour="forever_classic"):
    return {
        "source": source, "id": "1700375", "slug": "spoken-player",
        "name": name, "game_flavours": [flavour],
        "url": "https://www.curseforge.com/wow/addons/spoken-player",
    }


async def test_spoken_search_uses_structured_catalogue_and_exact_flavour(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"version": 8, "entries": [
            entry(), entry(name="Spoken Everything"), entry(name="Unrelated"),
            entry(source="wowi", name="Spoken Retail", flavour="mainline"),
        ]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    search = CatalogueSearch()
    results = await search.search("spoken", flavour="forever_classic")
    assert {result["name"] for result in results} == {"Spoken Player", "Spoken Everything"}
    assert [result["name"] for result in await search.search("spoken", flavour="mainline")] == ["Spoken Retail"]


async def test_catalogue_cache_coalesces_simultaneous_requests(monkeypatch):
    calls = []

    async def fetch(*args, **kwargs):
        calls.append(args)
        await asyncio.sleep(0)
        return {"version": 8, "entries": [entry()]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    search = CatalogueSearch()
    await asyncio.gather(*(search.search("spoken", flavour="forever_classic") for _ in range(3)))
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{"version": 7, "entries": []}, {"version": 8, "entries": {}}, []])
async def test_schema_drift_is_reported_instead_of_empty_results(monkeypatch, payload):
    async def fetch(*args, **kwargs):
        return payload

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    with pytest.raises(AzerothAddonsError) as error:
        await CatalogueSearch().search("spoken", flavour="forever_classic")
    assert error.value.code == SEARCH_FAILED


async def test_exact_matches_rank_first_and_limit_is_respected(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"version": 8, "entries": [entry(name="Spoken Player Audio"), entry()]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    results = await CatalogueSearch().search("Spoken Player", flavour="forever_classic", limit=1)
    assert [result["name"] for result in results] == ["Spoken Player"]


async def test_source_filter_applies_before_result_limit(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"version": 8, "entries": [entry(), entry(source="github", name="Spoken GitHub")]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    results = await CatalogueSearch().search("spoken", flavour="forever_classic", limit=1, sources={"github"})
    assert [result["source"] for result in results] == ["github"]


async def test_spoken_core_bundle_is_not_buried_by_audio_translations(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"version": 8, "entries": [
            entry(name=f"Spoken Books Audio Translated: Language {number}") for number in range(30)
        ] + [entry(), entry(name="Spoken Everything: Quests, Zones, Books AI Voiceover")]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    results = await CatalogueSearch().search("spoken", flavour="forever_classic", limit=2)
    assert [result["name"] for result in results] == [
        "Spoken Player", "Spoken Everything: Quests, Zones, Books AI Voiceover",
    ]
