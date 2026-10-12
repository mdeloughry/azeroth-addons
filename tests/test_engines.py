from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from azeroth_addons.engines.base import (
    STATE_INCOMPATIBLE,
    STATE_MISSING,
    STATE_READY,
    EngineCapabilities,
)
from azeroth_addons.engines.instawow import (
    PROVIDER_TO_SOURCE,
    InstawowAdapter,
    InstawowEngine,
    definition_for,
    parse_packages,
    parse_search_results,
    parse_update_targets,
    provider_to_source,
    source_to_provider,
    strip_ansi,
)
from azeroth_addons.engines.registry import EngineRegistry
from azeroth_addons.errors import (
    ENGINE_UNAVAILABLE,
    ENGINE_UNSUPPORTED,
    INSTALL_FAILED,
    PROVIDER_UNAVAILABLE,
    AzerothAddonsError,
)
from azeroth_addons.settings import JsonStore, SettingsStore


def make_settings(tmp_path: Path, **values) -> SettingsStore:
    store = JsonStore(tmp_path / "settings")
    settings = SettingsStore(store)
    settings.load()
    if values:
        settings.update(values)
    return settings


def make_engine(adapter: InstawowAdapter, tmp_path: Path, **values) -> InstawowEngine:
    return InstawowEngine(adapter, settings=make_settings(tmp_path, **values))


# --- registry --------------------------------------------------------------


async def test_engine_registry_registers_and_resolves():
    from conftest import FakeEngine

    registry = EngineRegistry()
    engine = FakeEngine()
    registry.register(engine, default=True)
    assert registry.get().engine_id == "fake"
    assert registry.get("fake") is engine
    assert registry.ids() == ["fake"]
    assert registry.default_id == "fake"
    statuses = await registry.statuses()
    assert statuses[0].available is True


def test_engine_registry_unknown_engine_raises():
    registry = EngineRegistry()
    with pytest.raises(AzerothAddonsError) as excinfo:
        registry.get("nope")
    assert excinfo.value.code == ENGINE_UNAVAILABLE
    assert registry.get_or_none("nope") is None


def test_rollback_capability_follows_the_feature_flag(tmp_path: Path, make_adapter):
    adapter = make_adapter()
    assert make_engine(adapter, tmp_path).capabilities().rollback is False
    assert make_engine(adapter, tmp_path, enableExperimentalRollback=True).capabilities().rollback is True


# --- adapter bootstrap -----------------------------------------------------


def test_ensure_executable_adds_the_execute_bit(tmp_path: Path):
    binary = tmp_path / "instawow"
    binary.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(binary, 0o600)
    adapter = InstawowAdapter(binary, tmp_path / "home")
    assert adapter.ensure_executable() is True
    assert binary.stat().st_mode & stat.S_IXUSR


def test_ensure_executable_reports_a_missing_binary(tmp_path: Path):
    adapter = InstawowAdapter(tmp_path / "missing", tmp_path / "home")
    assert adapter.exists() is False
    assert adapter.ensure_executable() is False


def test_environment_sets_home_and_tokens_without_leaking(tmp_path: Path, make_adapter):
    adapter = make_adapter(tokens={"curseforge": "cf-secret", "github": "gh-secret"})
    env = adapter.environment()
    assert env["INSTAWOW_HOME"].endswith("instawow-home")
    assert env["INSTAWOW_ACCESS_TOKENS_CFCORE"] == "cf-secret"
    assert env["INSTAWOW_ACCESS_TOKENS_GITHUB"] == "gh-secret"
    loggable = adapter.loggable_environment()
    assert loggable["INSTAWOW_ACCESS_TOKENS_CFCORE"] == "<redacted>"
    assert "cf-secret" not in json.dumps(loggable)


def test_redact_removes_configured_credentials(tmp_path: Path, make_adapter):
    adapter = make_adapter(tokens={"curseforge": "super-secret-key"})
    assert "super-secret-key" not in adapter.redact("key=super-secret-key done")


def test_profile_config_is_written_and_readable(tmp_path: Path, make_adapter, installation):
    adapter = make_adapter()
    addons = Path(installation.addons_path)
    path = adapter.write_profile_config("az-retail-abc123", addons, "mainline")
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["profile"] == "az-retail-abc123"
    assert payload["addon_dir"] == str(addons.resolve())
    assert payload["flavour_override"] == "mainline"
    assert adapter.read_profile_config("az-retail-abc123") == payload


def test_global_config_is_written_once(tmp_path: Path, make_adapter):
    adapter = make_adapter()
    adapter.write_global_config()
    first = adapter.global_config_path().read_text()
    adapter.global_config_path().write_text('{"auto_update_check": false}')
    adapter.write_global_config()
    assert adapter.global_config_path().read_text() == '{"auto_update_check": false}'
    assert json.loads(first) == {"auto_update_check": True}


async def test_version_is_parsed_from_engine_output(make_adapter, write_spec):
    write_spec(**{"--version": {"code": 0, "stdout": "instawow, version 7.2.1\n"}})
    assert await make_adapter().version() == "7.2.1"


async def test_incompatible_engine_is_reported(make_adapter, write_spec):
    write_spec(
        **{
            "--version": {
                "code": 127,
                "stdout": "",
                "stderr": "/lib/libc.so.6: version `GLIBC_2.38' not found",
            }
        }
    )
    with pytest.raises(AzerothAddonsError) as excinfo:
        await make_adapter().version()
    assert excinfo.value.code == "INSTAWOW_INCOMPATIBLE"


# --- parsing ---------------------------------------------------------------


def test_parse_packages_handles_the_primary_shape():
    payload = [
        {"source": "curse", "id": "masque", "version": "2.0.0", "folder_name": "Masque", "name": "Masque"},
        {"source": "github", "id": "sfx-wow/masque", "version": "1.2.3"},
    ]
    packages, unparsed = parse_packages(payload)
    assert unparsed == 0
    assert [package.provider for package in packages] == ["curseforge", "github"]
    assert packages[0].folder_name == "Masque"


def test_parse_packages_handles_wrappers_and_aliases():
    payload = {
        "packages": [
            {"source_id": "tukui", "slug": "elvui", "installed_version": "15.2"},
            {"defn": "curse:weakauras", "version": {"version": "5.0.0"}},
            {"defn": {"source": "wowi", "id": "17784"}, "version": "1.0"},
        ]
    }
    packages, unparsed = parse_packages(payload)
    assert unparsed == 0
    assert {package.provider for package in packages} == {"tukui", "curseforge", "wowinterface"}
    assert packages[0].ident == "elvui"
    assert packages[1].ident == "weakauras"
    assert packages[1].version == "5.0.0"


def test_parse_packages_counts_unparsed_records():
    payload = [{"source": "curse", "id": "ok"}, {"unexpected": True}, "not a record"]
    packages, unparsed = parse_packages(payload)
    assert len(packages) == 1
    assert unparsed == 2


def test_parse_update_targets_extracts_versions():
    text = strip_ansi(
        "\x1b[1mWould update:\x1b[0m\n"
        "  curse:masque 2.0.0 -> 2.1.0\n"
        "  github:sfx-wow/masque => 1.2.4\n"
        "no change: something-else\n"
    )
    targets = parse_update_targets(text)
    by_id = {(target.source, target.ident): target for target in targets}
    assert by_id[("curse", "masque")].to_version == "2.1.0"
    assert by_id[("github", "sfx-wow/masque")].to_version == "1.2.4"
    assert len(targets) == 2


def test_parse_search_results_drops_unattributable_lines():
    text = (
        "Details! Damage Meter   curse:details\n"
        "Loose Result With No Source\n"
        "  wago:some-addon  Wago Addon\n"
    )
    results = parse_search_results(text)
    assert [(source, ident) for source, ident, _ in results] == [("curse", "details"), ("wago", "some-addon")]
    assert results[0][2] == "Details! Damage Meter"


def test_source_and_provider_mapping_is_bidirectional():
    assert provider_to_source("curseforge") == "curse"
    assert source_to_provider("curse") == "curseforge"
    assert source_to_provider("wago") == "wago"
    assert set(PROVIDER_TO_SOURCE) == {"curseforge", "github", "tukui", "wowinterface", "wago", "instawow"}
    assert definition_for("github", "owner/repo") == "github:owner/repo"


def test_unknown_provider_is_rejected():
    with pytest.raises(AzerothAddonsError) as excinfo:
        provider_to_source("not-a-source")
    assert excinfo.value.code == PROVIDER_UNAVAILABLE


# --- engine lifecycle ------------------------------------------------------


async def test_prepare_reports_a_missing_binary(tmp_path: Path):
    adapter = InstawowAdapter(tmp_path / "missing-instawow", tmp_path / "home")
    engine = make_engine(adapter, tmp_path)
    status = await engine.prepare()
    assert status.state == STATE_MISSING
    assert status.available is False
    assert status.message


async def test_prepare_reports_an_incompatible_binary(tmp_path: Path, make_adapter, write_spec):
    write_spec(**{"--version": {"code": 127, "stderr": "GLIBC_2.38 not found"}})
    engine = make_engine(make_adapter(), tmp_path)
    status = await engine.prepare()
    assert status.state == STATE_INCOMPATIBLE
    assert status.available is False


async def test_prepare_becomes_ready_and_publishes_status(tmp_path: Path, make_adapter, write_spec):
    write_spec(**{"--version": {"code": 0, "stdout": "instawow, version 7.2.1\n"}})
    published: list[str] = []

    async def on_status(status):
        published.append(status.state)

    from azeroth_addons.engines.instawow import InstawowEngine

    engine = InstawowEngine(make_adapter(), settings=make_settings(tmp_path), status_callback=on_status)
    status = await engine.prepare()
    assert status.state == STATE_READY
    assert status.version == "7.2.1"
    assert status.bundled_version == "7.2.1"
    assert "verifying" in published and "ready" in published


async def test_operations_fail_cleanly_when_the_engine_is_missing(tmp_path: Path, installation):
    adapter = InstawowAdapter(tmp_path / "missing", tmp_path / "home")
    engine = make_engine(adapter, tmp_path)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await engine.list_installed(installation)
    assert excinfo.value.code == ENGINE_UNAVAILABLE


# --- engine commands -------------------------------------------------------


async def test_list_installed_passes_the_profile_and_home(tmp_path: Path, make_adapter, write_spec, installation, read_calls):
    write_spec(
        **{
            "list --format json": {
                "code": 0,
                "stdout": json.dumps(
                    [{"source": "curse", "id": "masque", "version": "2.0.0", "folder_name": "Masque"}]
                ),
            }
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    addons = await engine.list_installed(installation)
    assert [addon.id for addon in addons] == ["curseforge:masque"]
    assert addons[0].installed_version == "2.0.0"

    calls = read_calls()
    assert calls[-1]["args"][:2] == ["--profile", installation.engine_profile]
    assert "list" in calls[-1]["args"]
    assert calls[-1]["env_home"].endswith("instawow-home")


async def test_install_uses_the_source_alias(tmp_path: Path, make_adapter, write_spec, installation, read_calls):
    write_spec(
        **{
            "install curse:masque": {"code": 0, "stdout": "installed\n"},
            "list --format json": {
                "code": 0,
                "stdout": json.dumps([{"source": "curse", "id": "masque", "version": "3.0.0"}]),
            },
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    addon = await engine.install(installation, "curseforge", "masque")
    assert addon.id == "curseforge:masque"
    assert addon.installed_version == "3.0.0"
    assert any(call["args"][-2:] == ["install", "curse:masque"] for call in read_calls())


async def test_install_maps_github_identifiers(tmp_path: Path, make_adapter, write_spec, installation, read_calls):
    write_spec(**{"install github:owner/repo": {"code": 0}, "list --format json": {"code": 0, "stdout": "[]"}})
    engine = make_engine(make_adapter(), tmp_path)
    await engine.install(installation, "github", "owner/repo")
    assert any("github:owner/repo" in call["args"] for call in read_calls())


async def test_install_rejects_an_unknown_provider(tmp_path: Path, make_adapter, installation):
    engine = make_engine(make_adapter(), tmp_path)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await engine.install(installation, "notaprovider", "x")
    assert excinfo.value.code == PROVIDER_UNAVAILABLE


async def test_install_failure_is_structured_and_never_leaks_the_token(
    tmp_path: Path, make_adapter, write_spec, installation
):
    write_spec(
        **{
            "install curse:masque": {
                "code": 1,
                "stderr": "error: rejected api key super-secret-token while downloading",
            }
        }
    )
    engine = make_engine(make_adapter(tokens={"curseforge": "super-secret-token"}), tmp_path)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await engine.install(installation, "curseforge", "masque")
    error = excinfo.value
    assert error.code == INSTALL_FAILED
    assert "super-secret-token" not in (error.details or "")
    assert "super-secret-token" not in error.message
    assert error.installation_id == installation.id
    assert error.provider == "curseforge"


async def test_update_and_remove_generate_the_expected_arguments(
    tmp_path: Path, make_adapter, write_spec, installation, read_calls, addon_factory
):
    addon = addon_factory("curseforge", "masque")
    write_spec(
        **{
            "update curse:masque": {"code": 0},
            "remove curse:masque": {"code": 0},
            "list --format json": {
                "code": 0,
                "stdout": json.dumps([{"source": "curse", "id": "masque", "version": "9.0.0"}]),
            },
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    updated = await engine.update(installation, addon)
    assert updated.installed_version == "9.0.0"
    await engine.remove(installation, addon)
    args = [call["args"] for call in read_calls()]
    assert ["--profile", installation.engine_profile, "update", "curse:masque"] in args
    assert ["--profile", installation.engine_profile, "remove", "curse:masque"] in args


async def test_unmanaged_addons_are_never_modified(tmp_path: Path, make_adapter, installation):
    from azeroth_addons.addons.models import unmanaged_addon

    engine = make_engine(make_adapter(), tmp_path)
    with pytest.raises(AzerothAddonsError):
        await engine.update(installation, unmanaged_addon("ConsolePort"))
    with pytest.raises(AzerothAddonsError):
        await engine.remove(installation, unmanaged_addon("ConsolePort"))


async def test_check_updates_marks_update_available(
    tmp_path: Path, make_adapter, write_spec, installation, addon_factory
):
    write_spec(
        **{
            "update --dry-run": {"code": 0, "stdout": "curse:masque 2.0.0 -> 2.1.0\n"},
            "list --format json": {
                "code": 0,
                "stdout": json.dumps(
                    [{"source": "curse", "id": "masque", "version": "2.0.0", "folder_name": "Masque"}]
                ),
            },
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    updates = await engine.check_updates(installation)
    assert len(updates) == 1
    assert updates[0].id == "curseforge:masque"
    assert updates[0].state == "update-available"
    assert updates[0].available_version == "2.1.0"


async def test_check_updates_with_nothing_to_do(tmp_path: Path, make_adapter, write_spec, installation):
    write_spec(**{"update --dry-run": {"code": 0, "stdout": "Nothing to update.\n"}})
    engine = make_engine(make_adapter(), tmp_path)
    assert await engine.check_updates(installation) == []


async def test_check_updates_failure_is_reported(tmp_path: Path, make_adapter, write_spec, installation):
    write_spec(**{"update --dry-run": {"code": 2, "stderr": "network error"}})
    engine = make_engine(make_adapter(), tmp_path)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await engine.check_updates(installation)
    assert excinfo.value.code == "UPDATE_FAILED"


async def test_update_all_reports_only_changed_addons(tmp_path: Path, make_adapter, write_spec, installation):
    calls = {"n": 0}

    # The fake returns the old list first, then the new one.
    spec_old = json.dumps([{"source": "curse", "id": "masque", "version": "1.0.0"}])
    spec_new = json.dumps(
        [
            {"source": "curse", "id": "masque", "version": "2.0.0"},
            {"source": "github", "id": "other/repo", "version": "1.0.0"},
        ]
    )
    # Two list calls: first old, then new. The fake can only return one value,
    # so drive it through a rotating spec file.
    import azeroth_addons.engines.instawow as instawow_module

    real_parse = instawow_module.InstawowAdapter.list_packages
    sequence = [spec_old, spec_new]

    async def rotating(self, profile):
        payload = json.loads(sequence[min(calls["n"], len(sequence) - 1)])
        calls["n"] += 1
        return instawow_module.parse_packages(payload)

    write_spec(**{"update": {"code": 0}})
    engine = make_engine(make_adapter(), tmp_path)
    instawow_module.InstawowAdapter.list_packages = rotating
    try:
        changed = await engine.update_all(installation)
    finally:
        instawow_module.InstawowAdapter.list_packages = real_parse

    assert [addon.id for addon in changed] == ["curseforge:masque"]
    assert changed[0].installed_version == "2.0.0"


async def test_rollback_is_gated_by_the_feature_flag(tmp_path: Path, make_adapter, write_spec, installation, addon_factory):
    write_spec(**{"rollback curse:masque": {"code": 0}, "list --format json": {"code": 0, "stdout": "[]"}})
    disabled = make_engine(make_adapter(), tmp_path)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await disabled.rollback(installation, addon_factory("curseforge", "masque"))
    assert excinfo.value.code == ENGINE_UNSUPPORTED

    enabled = make_engine(make_adapter(), tmp_path, enableExperimentalRollback=True)
    await enabled.rollback(installation, addon_factory("curseforge", "masque"))


async def test_reconcile_keeps_unmanaged_addons_and_ignores_owned_siblings(
    tmp_path: Path, make_adapter, write_spec, installation
):
    addons_dir = Path(installation.addons_path)
    for folder in ("Masque", "Masque_Options", "ConsolePort", "WeakAuras"):
        (addons_dir / folder).mkdir()

    write_spec(
        **{
            "reconcile --auto": {"code": 0},
            "list --format json": {
                "code": 0,
                "stdout": json.dumps(
                    [{"source": "curse", "id": "masque", "version": "1.0.0", "folder_name": "Masque"}]
                ),
            },
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    result = await engine.reconcile(installation)
    assert [addon.id for addon in result.managed] == ["curseforge:masque"]
    unmanaged = {addon.folder_name for addon in result.unmanaged}
    assert unmanaged == {"ConsolePort", "WeakAuras"}  # Masque_Options is owned by Masque


async def test_reconcile_survives_a_failing_reconcile_command(
    tmp_path: Path, make_adapter, write_spec, installation
):
    write_spec(
        **{
            "reconcile --auto": {"code": 1, "stderr": "boom"},
            "list --format json": {"code": 0, "stdout": "[]"},
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    result = await engine.reconcile(installation)
    assert result.managed == []


async def test_search_maps_results_to_providers(tmp_path: Path, make_adapter, write_spec, installation, monkeypatch):
    async def fetch(*args, **kwargs):
        return {"version": 8, "entries": [{
            "source": "curse", "id": "123", "slug": "details", "name": "Details! Damage Meter",
            "game_flavours": [installation.instawow_flavour],
            "url": "https://www.curseforge.com/wow/addons/details",
        }]}

    monkeypatch.setattr("azeroth_addons.engines.catalogue.fetch_json", fetch)
    # The old CLI picker must never run: it can fail without a TTY, or install
    # addons as a side effect of a supposedly read-only search.
    write_spec(**{"search details --limit 25": {"code": 1, "stderr": "EOFError"}})
    engine = make_engine(make_adapter(), tmp_path)
    results = await engine.search(installation, "details")
    assert [(addon.provider, addon.provider_id, addon.name) for addon in results] == [
        ("curseforge", "details", "Details! Damage Meter")
    ]
    assert results[0].homepage == "https://www.curseforge.com/wow/addons/details"


async def test_profile_status_reports_validation(tmp_path: Path, make_adapter, write_spec, installation):
    write_spec(
        **{
            "debug": {
                "code": 0,
                "stdout": json.dumps(
                    {"profile": {"addon_dir": str(installation.addons_path), "flavour_override": "mainline"}}
                ),
            }
        }
    )
    engine = make_engine(make_adapter(), tmp_path)
    await engine.prepare()
    payload = await engine.profile_status(installation)
    assert payload["profile"] == installation.engine_profile
    assert payload["validated"] is True
    assert payload["addonDir"] == str(installation.addons_path)
