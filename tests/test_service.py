from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import FakeEngine

from azeroth_addons import events
from azeroth_addons.addons.models import Addon, unmanaged_addon
from azeroth_addons.engines.base import EngineCapabilities
from azeroth_addons.errors import (
    ADDON_NOT_FOUND,
    ENGINE_UNSUPPORTED,
    INSTALLATION_UNAVAILABLE,
    WOW_RUNNING,
    AzerothAddonsError,
)


@pytest.fixture
def service_stack(stack, installation, seed_installation, emitter):
    def _build(*, engine=None, proc_root: str = "/proc"):
        registered = stack(
            engine=engine or FakeEngine(),
            proc_root=proc_root,
            emitter=emitter,
            register=lambda manager: seed_installation(manager, installation),
        )
        registered.installation = installation
        return registered

    return _build


async def test_installed_returns_managed_and_unmanaged(service_stack, addon_factory):
    engine = FakeEngine(
        addons=[addon_factory("curseforge", "masque")],
        unmanaged=[unmanaged_addon("ConsolePort")],
    )
    registered = service_stack(engine=engine)
    payload = await registered.service.installed(registered.installation.id)

    assert [addon["id"] for addon in payload["addons"]] == ["curseforge:masque"]
    assert [addon["folderName"] for addon in payload["unmanaged"]] == ["ConsolePort"]
    assert payload["counts"] == {"installed": 1, "unmanaged": 1, "updates": 0}
    assert payload["running"] is False


async def test_installed_is_cached_until_invalidated(service_stack, addon_factory):
    engine = FakeEngine(addons=[addon_factory("curseforge", "masque")])
    registered = service_stack(engine=engine)
    await registered.service.installed(registered.installation.id)
    reconciles = sum(1 for call in engine.calls if call[0] == "reconcile")
    await registered.service.installed(registered.installation.id)
    assert sum(1 for call in engine.calls if call[0] == "reconcile") == reconciles

    await registered.service.installed(registered.installation.id, refresh=True)
    assert sum(1 for call in engine.calls if call[0] == "reconcile") == reconciles + 1


async def test_installed_skips_reconcile_when_unsupported(service_stack, addon_factory):
    engine = FakeEngine(
        addons=[addon_factory("curseforge", "masque")],
        capabilities=EngineCapabilities(install=True, list_installed=True),
    )
    registered = service_stack(engine=engine)
    payload = await registered.service.installed(registered.installation.id)
    assert payload["unmanaged"] == []
    assert any(call[0] == "list_installed" for call in engine.calls)


async def test_unavailable_installation_is_rejected(service_stack):
    registered = service_stack()
    shutil.rmtree(registered.installation.root_path)
    registered.installations.refresh_availability()
    with pytest.raises(AzerothAddonsError) as excinfo:
        await registered.service.installed(registered.installation.id)
    assert excinfo.value.code == INSTALLATION_UNAVAILABLE


@pytest.mark.parametrize("operation", ["install", "update", "update_all", "remove", "rollback"])
async def test_every_mutating_operation_is_blocked_while_the_game_runs(
    service_stack, fake_proc, addon_factory, operation
):
    proc_root, add = fake_proc
    registered = service_stack(proc_root=str(proc_root))
    add(4242, f"/usr/bin/wine{NUL}{registered.installation.root_path}/Wow.exe{NUL}")

    with pytest.raises(AzerothAddonsError) as excinfo:
        if operation == "install":
            await registered.service.install(registered.installation.id, "curseforge", "masque")
        elif operation == "update":
            await registered.service.update(registered.installation.id, "curseforge:masque")
        elif operation == "update_all":
            await registered.service.update_all(registered.installation.id)
        elif operation == "remove":
            await registered.service.remove(registered.installation.id, "curseforge:masque")
        else:
            await registered.service.rollback(registered.installation.id, "curseforge:masque")

    assert excinfo.value.code == WOW_RUNNING
    assert "running" in excinfo.value.message.lower()


NUL = "{NUL}"


async def test_install_emits_progress_and_change_events(service_stack, emitter):
    registered = service_stack()
    addon = await registered.service.install(registered.installation.id, "curseforge", "masque")

    assert addon.id == "curseforge:masque"
    assert events.OPERATION in emitter.names()
    phases = [payload["phase"] for payload in emitter.payloads(events.OPERATION)]
    assert phases == ["start", "done"]
    assert events.ADDONS_CHANGED in emitter.names()
    assert emitter.payloads(events.ADDONS_CHANGED)[-1]["reason"] == "install"


async def test_install_is_refused_when_the_engine_cannot_install(service_stack):
    engine = FakeEngine(capabilities=EngineCapabilities(update=True, list_installed=True))
    registered = service_stack(engine=engine)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await registered.service.install(registered.installation.id, "curseforge", "masque")
    assert excinfo.value.code == ENGINE_UNSUPPORTED


async def test_update_requires_a_known_managed_addon(service_stack, addon_factory):
    registered = service_stack(engine=FakeEngine(addons=[addon_factory("curseforge", "masque")]))
    with pytest.raises(AzerothAddonsError) as excinfo:
        await registered.service.update(registered.installation.id, "curseforge:unknown")
    assert excinfo.value.code == ADDON_NOT_FOUND


async def test_unmanaged_addons_cannot_be_updated_or_removed(service_stack):
    registered = service_stack()
    for operation in (registered.service.update, registered.service.remove):
        with pytest.raises(AzerothAddonsError) as excinfo:
            await operation(registered.installation.id, "unmanaged:ConsolePort")
        assert excinfo.value.code == ADDON_NOT_FOUND


async def test_update_reports_the_new_version(service_stack, addon_factory):
    registered = service_stack(engine=FakeEngine(addons=[addon_factory("curseforge", "masque")]))
    await registered.service.installed(registered.installation.id)
    updated = await registered.service.update(registered.installation.id, "curseforge:masque")
    assert updated.installed_version == "2.0.0"


async def test_update_all_loops_targets_and_isolates_failures(service_stack, addon_factory, emitter):
    targets = [
        addon_factory("curseforge", "masque"),
        addon_factory("curseforge", "details"),
        addon_factory("github", "owner/repo"),
    ]
    engine = FakeEngine(addons=targets, updates=targets, fail_update_ids=["curseforge:details"])
    registered = service_stack(engine=engine)
    await registered.service.installed(registered.installation.id)

    result = await registered.service.update_all(registered.installation.id)
    assert result["updatedCount"] == 2
    assert [failure["addonId"] for failure in result["failures"]] == ["curseforge:details"]
    progress = [payload for payload in emitter.payloads(events.OPERATION) if payload["kind"] == "update_all"]
    assert max(payload["current"] for payload in progress) == 3
    assert progress[-1]["phase"] == "done"


async def test_update_all_falls_back_to_a_bulk_update_when_nothing_is_enumerated(service_stack):
    engine = FakeEngine(addons=[], updates=[], )
    registered = service_stack(engine=engine)
    result = await registered.service.update_all(registered.installation.id)
    assert result["updatedCount"] == 0
    assert any(call[0] == "update_all" for call in engine.calls)


async def test_rollback_is_gated_by_capability(service_stack):
    engine = FakeEngine(capabilities=EngineCapabilities(update=True, list_installed=True))
    registered = service_stack(engine=engine)
    with pytest.raises(AzerothAddonsError) as excinfo:
        await registered.service.rollback(registered.installation.id, "curseforge:masque")
    assert excinfo.value.code == ENGINE_UNSUPPORTED


async def test_rollback_runs_when_enabled(service_stack, addon_factory):
    registered = service_stack(engine=FakeEngine(addons=[addon_factory("curseforge", "masque")]))
    await registered.service.installed(registered.installation.id)
    rolled = await registered.service.rollback(registered.installation.id, "curseforge:masque")
    assert rolled.installed_version == "0.9.0"


async def test_check_updates_reports_and_announces(service_stack, addon_factory, emitter):
    target = addon_factory("curseforge", "masque")
    target.state = "update-available"
    target.available_version = "2.0.0"
    registered = service_stack(engine=FakeEngine(addons=[target], updates=[target]))
    await registered.service.installed(registered.installation.id)
    payload = await registered.service.check_updates(registered.installation.id)
    assert payload["count"] == 1
    assert payload["updates"][0]["availableVersion"] == "2.0.0"
    assert emitter.payloads(events.ADDONS_CHANGED)[-1]["reason"] == "updates"


async def test_remove_returns_the_removed_addon(service_stack, addon_factory, emitter):
    registered = service_stack(engine=FakeEngine(addons=[addon_factory("curseforge", "masque")]))
    await registered.service.installed(registered.installation.id)
    payload = await registered.service.remove(registered.installation.id, "curseforge:masque")
    assert payload["removed"]["id"] == "curseforge:masque"
    assert emitter.payloads(events.ADDONS_CHANGED)[-1]["reason"] == "remove"


async def test_runtime_status_includes_installations_and_binary(service_stack):
    registered = service_stack()
    payload = registered.service.runtime_status()
    assert payload["installations"]["total"] == 1
    assert payload["running"] == []
    assert "pluginVersion" in payload


def test_service_exposes_no_installations_before_registration(stack, emitter):
    registered = stack(emitter=emitter)
    assert registered.installations.all() == []
    assert registered.service.runtime_status()["installations"]["total"] == 0
