"""Tests for the RPC boundary in ``main.py``.

The Decky loader calls these methods directly, so they must always answer with
an envelope, never raise, and never leak credentials.

These tests use the environment-variable entry points that the plugin resolves
at startup, which is also how a developer points Azeroth Addons at their own
engine build.
"""

from __future__ import annotations

import inspect
import importlib
import json
import sys
from pathlib import Path

import pytest

from azeroth_addons.errors import INTERNAL_ERROR, AzerothAddonsError, rpc

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_plugin(tmp_path: Path, monkeypatch, *, engine_binary: Path | None = None):
    monkeypatch.setenv("DECKY_PLUGIN_DIR", str(REPO_ROOT))
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("DECKY_PLUGIN_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DECKY_PLUGIN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("HOME", str(tmp_path))
    if engine_binary is None:
        monkeypatch.delenv("AZEROTH_INSTAWOW_BINARY", raising=False)
    else:
        monkeypatch.setenv("AZEROTH_INSTAWOW_BINARY", str(engine_binary))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    module = importlib.import_module("main")
    importlib.reload(module)
    return module.Plugin()


@pytest.fixture
def plugin(tmp_path: Path, monkeypatch):
    return build_plugin(tmp_path, monkeypatch)


@pytest.fixture
def engine_plugin(tmp_path: Path, monkeypatch, fake_instawow, write_spec):
    binary, _spec, _log = fake_instawow
    write_spec(
        **{
            "--version": {"code": 0, "stdout": "instawow, version 7.2.1\n"},
            "debug": {
                "code": 0,
                "stdout": json.dumps({"profile": {"addon_dir": "/tmp/addons", "flavour_override": "mainline"}}),
            },
            "list --format json": {
                "code": 0,
                "stdout": json.dumps(
                    [{"source": "curse", "id": "masque", "version": "2.0.0", "folder_name": "Masque"}]
                ),
            },
        }
    )
    return build_plugin(tmp_path, monkeypatch, engine_binary=binary)


# --- the decorator --------------------------------------------------------


async def test_rpc_wraps_success():
    @rpc
    async def handler() -> dict[str, str]:
        return {"hello": "world"}

    assert await handler() == {"ok": True, "data": {"hello": "world"}}


async def test_rpc_turns_structured_errors_into_envelopes():
    @rpc
    async def handler():
        raise AzerothAddonsError("WOW_NOT_FOUND", "not here", installation_id="retail-1")

    envelope = await handler()
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "WOW_NOT_FOUND"
    assert envelope["error"]["installationId"] == "retail-1"


async def test_rpc_hides_unexpected_exceptions():
    @rpc
    async def handler():
        raise RuntimeError("kaboom with a token=abcdef")

    envelope = await handler()
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == INTERNAL_ERROR
    assert "kaboom" not in envelope["error"]["message"]
    assert "kaboom" in envelope["error"]["details"]


# --- the plugin surface ---------------------------------------------------


def test_every_public_method_is_an_rpc_handler(plugin):
    """A method without @rpc would raise into the loader instead of answering."""
    missing = []
    for name, member in inspect.getmembers(type(plugin), inspect.isfunction):
        if name.startswith("_"):
            continue
        assert inspect.iscoroutinefunction(member), f"{name} must be async"
        if not hasattr(member, "__wrapped__"):
            missing.append(name)
    assert not missing, f"these routes are not wrapped by @rpc: {missing}"


async def test_runtime_status_route(plugin):
    envelope = await plugin.get_runtime_status()
    assert envelope["ok"] is True
    assert envelope["data"]["pluginVersion"]
    assert envelope["data"]["binary"]["sha256"]
    assert envelope["data"]["engine"] is None  # not probed yet


async def test_installation_routes_round_trip(plugin, wow_root: Path):
    added = await plugin.add_custom_installation(str(wow_root))
    assert added["ok"] is True
    assert len(added["data"]["installations"]) == 3

    listed = await plugin.get_installations()
    assert listed["ok"] is True
    assert len(listed["data"]["installations"]) == 3

    selected = listed["data"]["selectedId"]
    renamed = await plugin.update_installation(selected, "My Retail")
    assert renamed["ok"] is True
    assert any(item["displayName"] == "My Retail" for item in renamed["data"]["installations"])

    removed = await plugin.remove_installation(selected)
    assert removed["ok"] is True
    assert len(removed["data"]["installations"]) == 2


async def test_custom_path_validation_route(plugin, tmp_path: Path):
    plain = tmp_path / "documents"
    plain.mkdir()
    envelope = await plugin.add_custom_installation(str(plain))
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INVALID_WOW_PATH"

    empty = await plugin.validate_custom_path("  ")
    assert empty["ok"] is False
    assert empty["error"]["code"] == "INVALID_ARGUMENT"

    preview = await plugin.validate_custom_path(str(plain))
    assert preview["ok"] is False  # a folder with no WoW install is refused


async def test_addon_routes_reject_unknown_installations(plugin):
    envelope = await plugin.get_installed_addons("retail-nope")
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INSTALLATION_NOT_FOUND"

    envelope = await plugin.search_addons("retail-nope", "details")
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INSTALLATION_NOT_FOUND"


async def test_engine_and_provider_status_routes(plugin):
    engines = await plugin.get_engines()
    assert engines["ok"] is True
    assert engines["data"]["default"] == "instawow"
    instawow = engines["data"]["engines"][0]
    assert instawow["id"] == "instawow"
    assert instawow["capabilities"]["install"] is True
    assert instawow["capabilities"]["rollback"] is False  # experimental, off by default

    providers = await plugin.get_providers()
    assert providers["ok"] is True
    ids = {provider["id"] for provider in providers["data"]["providers"]}
    assert ids == {"curseforge", "github", "tukui", "wago", "wowinterface"}
    # Zero-configuration sources are enabled; the gated one is not.
    assert "github" in providers["data"]["enabled"]
    assert "curseforge" not in providers["data"]["enabled"]


async def test_settings_route_never_returns_a_credential(plugin):
    saved = await plugin.set_credential("curseforge", "super-secret-key-value")
    assert saved["ok"] is True
    payload = saved["data"]
    assert payload["credentials"]["curseforge"]["configured"] is True
    assert "super-secret-key-value" not in str(payload)
    assert payload["credentials"]["curseforge"]["hint"].startswith("su")

    cleared = await plugin.clear_credential("curseforge")
    assert cleared["data"]["credentials"]["curseforge"]["configured"] is False


async def test_settings_route_ignores_unknown_keys(plugin):
    envelope = await plugin.set_settings({"notARealSetting": True, "enableExperimentalRollback": True})
    assert envelope["ok"] is True
    assert "notARealSetting" not in envelope["data"]["values"]
    assert envelope["data"]["values"]["enableExperimentalRollback"] is True


async def test_settings_rejects_a_non_dict(plugin):
    envelope = await plugin.set_settings(["nope"])  # type: ignore[arg-type]
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"


# --- with a working (fake) engine -----------------------------------------


async def test_engine_prepare_and_profile_routes(engine_plugin, wow_root: Path):
    prepared = await engine_plugin.prepare_engine()
    assert prepared["ok"] is True
    assert prepared["data"]["state"] == "ready"
    assert prepared["data"]["version"] == "7.2.1"

    await engine_plugin.add_custom_installation(str(wow_root))
    listed = await engine_plugin.get_installations()
    installation = listed["data"]["installations"][0]

    profile = await engine_plugin.get_engine_profile(installation["id"])
    assert profile["ok"] is True
    assert profile["data"]["engineProfile"] == installation["engineProfile"]
    assert profile["data"]["validated"] is True


async def test_installed_addons_and_reconcile_routes(engine_plugin, wow_root: Path):
    await engine_plugin.add_custom_installation(str(wow_root))
    listed = await engine_plugin.get_installations()
    installation_id = listed["data"]["selectedId"]

    payload = await engine_plugin.get_installed_addons(installation_id)
    assert payload["ok"] is True
    assert [addon["id"] for addon in payload["data"]["addons"]] == ["curseforge:masque"]
    assert payload["data"]["counts"]["installed"] == 1

    reconciled = await engine_plugin.reconcile_addons(installation_id)
    assert reconciled["ok"] is True
    assert reconciled["data"]["counts"]["installed"] == 1


async def test_mutating_routes_report_a_missing_engine(tmp_path: Path, monkeypatch, wow_root: Path):
    """With no bundled binary, operations fail with a clear, actionable code."""
    plugin = build_plugin(
        tmp_path / "missing-engine",
        monkeypatch,
        engine_binary=tmp_path / "not-installed" / "instawow",
    )
    await plugin.add_custom_installation(str(wow_root))
    listed = await plugin.get_installations()
    installation_id = listed["data"]["selectedId"]

    envelope = await plugin.get_installed_addons(installation_id)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "ENGINE_UNAVAILABLE"
    assert "missing" in envelope["error"]["message"].lower()
