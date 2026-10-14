"""Update discovery must never offer untrusted, old or unverifiable packages."""
import asyncio
import json

import pytest

from azeroth_addons import plugin_updates as updates
from azeroth_addons.errors import AzerothAddonsError
from azeroth_addons.settings import JsonStore, SettingsStore


@pytest.fixture
def release():
    return {"tag_name": "v0.2.0", "draft": False, "prerelease": False, "body": "Release notes",
            "assets": [{"name": "azeroth-addons.zip", "state": "uploaded",
                        "browser_download_url": f"{updates.RELEASES_URL}/download/v0.2.0/azeroth-addons.zip",
                        "digest": "sha256:" + "a" * 64}]}


@pytest.fixture
def checker(tmp_path):
    return updates.PluginUpdates(SettingsStore(JsonStore(tmp_path)), "0.1.8")


def transport(monkeypatch, release):
    calls = []
    async def fetch(url, limit):
        calls.append(url)
        return json.dumps(release).encode()
    monkeypatch.setattr(updates, "fetch_release", fetch)
    return calls


@pytest.mark.asyncio
async def test_exact_versioned_plan_and_cached_automatic_checks(checker, release, monkeypatch):
    calls = transport(monkeypatch, release)
    status = await checker.check()
    assert status["state"] == "available"
    assert status["release"]["sha256"] == "a" * 64
    assert checker.install_plan("0.2.0")["assetUrl"].endswith("/v0.2.0/azeroth-addons.zip")
    await checker.check()
    assert len(calls) == 1
    await checker.check(force=True)
    assert len(calls) == 2
    with pytest.raises(AzerothAddonsError, match="changed"):
        checker.install_plan("0.1.9")


@pytest.mark.asyncio
async def test_disabled_checks_make_no_network_request_but_manual_still_works(checker, release, monkeypatch):
    calls = transport(monkeypatch, release)
    checker.settings.update({"autoCheckPluginUpdates": False})
    assert (await checker.check())["state"] == "disabled"
    assert calls == []
    assert (await checker.check(force=True))["state"] == "available"
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("current", ["0.2.0", "0.3.0", "1.0.0-beta.1"])
async def test_no_equal_or_older_release_offer(checker, release, monkeypatch, current):
    transport(monkeypatch, release)
    checker.current_version = current
    assert (await checker.check())["state"] == "up-to-date"
    with pytest.raises(AzerothAddonsError, match="Check"):
        checker.install_plan("0.2.0")


@pytest.mark.asyncio
async def test_same_version_stable_can_replace_prerelease(checker, release, monkeypatch):
    transport(monkeypatch, release)
    checker.current_version = "0.2.0-beta.1"
    assert (await checker.check())["state"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"draft": True}, {"prerelease": True}, {"tag_name": "v0.2.0-beta.1"},
    {"tag_name": "main"}, {"tag_name": "v0.2.0/../../elsewhere"}, {"assets": []},
    {"assets": [{"name": "azeroth-addons.zip", "state": "uploaded", "browser_download_url": "https://evil.example/file.zip", "digest": "sha256:" + "a" * 64}]},
])
async def test_rejects_ineligible_or_untrusted_releases(checker, release, monkeypatch, change):
    release.update(change)
    transport(monkeypatch, release)
    assert (await checker.check())["state"] == "error"
    with pytest.raises(AzerothAddonsError):
        checker.install_plan("0.2.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("digest", [None, "sha256:abc", "md5:" + "a" * 64, "", False])
async def test_no_unverified_download(checker, release, monkeypatch, digest):
    release["assets"][0]["digest"] = digest
    transport(monkeypatch, release)
    assert (await checker.check())["state"] == "error"


@pytest.mark.asyncio
async def test_checksum_asset_fallback(checker, release, monkeypatch):
    release["assets"][0].pop("digest")
    release["assets"].append({"name": "azeroth-addons.zip.sha256", "state": "uploaded",
                              "browser_download_url": f"{updates.RELEASES_URL}/download/v0.2.0/azeroth-addons.zip.sha256"})
    async def fetch(url, limit):
        if url == updates.LATEST_URL:
            return json.dumps(release).encode()
        assert url.endswith("/v0.2.0/azeroth-addons.zip.sha256")
        assert limit == 1024
        return ("b" * 64 + "  azeroth-addons.zip\n").encode()
    monkeypatch.setattr(updates, "fetch_release", fetch)
    assert (await checker.check())["release"]["sha256"] == "b" * 64


@pytest.mark.asyncio
async def test_failure_removes_stale_plan_and_caches_retry(checker, release, monkeypatch):
    transport(monkeypatch, release)
    await checker.check()
    attempts = []
    async def fail(url, limit):
        attempts.append(url)
        raise OSError("offline")
    monkeypatch.setattr(updates, "fetch_release", fail)
    assert (await checker.check(force=True))["state"] == "error"
    assert checker.status()["release"] is None
    await checker.check()
    assert len(attempts) == 1
    with pytest.raises(AzerothAddonsError):
        checker.install_plan("0.2.0")


@pytest.mark.asyncio
async def test_concurrent_views_share_one_check(checker, release, monkeypatch):
    calls = transport(monkeypatch, release)
    results = await asyncio.gather(checker.check(), checker.check(), checker.check())
    assert all(result["state"] == "available" for result in results)
    assert len(calls) == 1
