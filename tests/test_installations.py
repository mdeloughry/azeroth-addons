from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import make_version_dir, make_wow_root

from azeroth_addons.errors import (
    DUPLICATE_INSTALLATION,
    INSTALLATION_NOT_FOUND,
    INSTALLATION_UNAVAILABLE,
    INVALID_WOW_PATH,
    SECURITY_VIOLATION,
    AzerothAddonsError,
)
from azeroth_addons.installations.manager import InstallationManager
from azeroth_addons.settings import InstallationStore, JsonStore, SettingsStore


@pytest.fixture
def manager(tmp_path: Path) -> InstallationManager:
    store = JsonStore(tmp_path / "settings")
    settings = SettingsStore(store)
    settings.load()
    return InstallationManager(InstallationStore(store), settings)


@pytest.fixture
def reload_manager(tmp_path: Path):
    def _reload() -> InstallationManager:
        store = JsonStore(tmp_path / "settings")
        settings = SettingsStore(store)
        settings.load()
        return InstallationManager(InstallationStore(store), settings)

    return _reload


def test_add_custom_registers_every_version_in_a_root(manager, wow_root: Path):
    result = manager.add_custom(wow_root)
    assert result["discovered"] == 3
    assert len(result["added"]) == 3
    assert manager.count_by_flavour() == {"retail": 1, "classic-era": 1, "forever": 1}


def test_add_custom_is_idempotent(manager, wow_root: Path):
    manager.add_custom(wow_root)
    second = manager.add_custom(wow_root)
    assert second["added"] == []
    assert len(second["existing"]) == 3
    assert len(manager.all()) == 3


def test_add_custom_rejects_a_non_wow_directory(manager, tmp_path: Path):
    plain = tmp_path / "documents"
    plain.mkdir()
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.add_custom(plain)
    assert excinfo.value.code == INVALID_WOW_PATH


def test_add_custom_rejects_an_empty_wow_directory(manager, tmp_path: Path):
    root = tmp_path / "World of Warcraft"
    (root / "_retail_").mkdir(parents=True)  # no markers at all
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.add_custom(root)
    assert excinfo.value.code == INVALID_WOW_PATH


def test_add_custom_rejects_protected_locations(manager):
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.add_custom("/etc")
    assert excinfo.value.code == SECURITY_VIOLATION


def test_duplicate_installation_is_detected(manager, wow_root: Path):
    manager.add_custom(wow_root)
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.assert_not_duplicate(wow_root / "_retail_")
    assert excinfo.value.code == DUPLICATE_INSTALLATION


def test_missing_drive_is_persisted_and_marked_unavailable(manager, reload_manager, wow_root: Path):
    manager.add_custom(wow_root)
    shutil.rmtree(wow_root)

    reloaded = reload_manager()
    assert len(reloaded.all()) == 3
    assert reloaded.available() == []
    for installation in reloaded.all():
        assert installation.available is False


def test_reconnected_drive_becomes_available_again(manager, wow_root: Path):
    manager.add_custom(wow_root)
    shutil.rmtree(wow_root)
    manager.refresh_availability()
    assert all(not installation.available for installation in manager.all())

    make_version_dir(wow_root, "_retail_")
    make_version_dir(wow_root, "_classic_era_")
    make_version_dir(wow_root, "_classic_beta_")
    manager.refresh_availability()
    assert len(manager.available()) == 3


def test_require_available_explains_a_missing_drive(manager, wow_root: Path):
    manager.add_custom(wow_root)
    shutil.rmtree(wow_root)
    manager.refresh_availability()
    installation = manager.all()[0]
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.require_available(installation.id)
    assert excinfo.value.code == INSTALLATION_UNAVAILABLE
    assert "drive" in excinfo.value.message.lower()


def test_unknown_installation_id(manager):
    with pytest.raises(AzerothAddonsError) as excinfo:
        manager.get("retail-zzzzzz")
    assert excinfo.value.code == INSTALLATION_NOT_FOUND


def test_selection_defaults_to_the_first_available_installation(manager, wow_root: Path):
    manager.add_custom(wow_root)
    assert manager.selected_id() == manager.available()[0].id


def test_removing_the_selected_installation_clears_the_selection(manager, wow_root: Path):
    manager.add_custom(wow_root)
    selected = manager.selected_id()
    assert selected is not None
    manager.set_selected(selected)
    manager.remove(selected)
    assert manager.selected_id() != selected


def test_removing_an_installation_keeps_the_others(manager, wow_root: Path):
    manager.add_custom(wow_root)
    victim = manager.all()[0].id
    manager.remove(victim)
    assert len(manager.all()) == 2
    assert victim not in {installation.id for installation in manager.all()}


def test_rename_validates_input(manager, wow_root: Path):
    manager.add_custom(wow_root)
    installation = manager.all()[0]
    manager.rename(installation.id, "  Retail (main)  ")
    assert manager.get(installation.id).display_name == "Retail (main)"
    with pytest.raises(AzerothAddonsError):
        manager.rename(installation.id, "   ")


def test_display_names_are_unique_across_duplicates(tmp_path: Path, manager):
    make_wow_root(tmp_path / "one", folders=("_retail_",), name="World of Warcraft")
    make_wow_root(tmp_path / "two", folders=("_retail_",), name="World of Warcraft")
    manager.add_custom(tmp_path / "one" / "World of Warcraft")
    manager.add_custom(tmp_path / "two" / "World of Warcraft")
    names = [installation.display_name for installation in manager.all()]
    assert len(names) == 2
    assert len(set(names)) == 2


def test_rescan_reports_new_and_unavailable(manager, tmp_path: Path):
    existing = make_wow_root(tmp_path / "one", folders=("_retail_",), name="WoW A")
    manager.add_custom(existing)
    shutil.rmtree(existing)

    fresh = make_wow_root(tmp_path / "two", folders=("_classic_era_",), name="WoW B")
    from azeroth_addons.installations.discovery import DiscoveryEnvironment

    result = manager.rescan(DiscoveryEnvironment(home=tmp_path, scan_roots=(tmp_path,)))
    assert len(result.added) == 1
    assert len(result.unavailable) == 1
    assert len(manager.all()) == 2


def test_engine_profile_is_per_installation(manager, wow_root: Path):
    manager.add_custom(wow_root)
    profiles = {installation.engine_profile for installation in manager.all()}
    assert len(profiles) == 3
    for installation in manager.all():
        assert installation.engine_profile == f"az-{installation.id}"


def test_summary_counts(manager, wow_root: Path):
    manager.add_custom(wow_root)
    summary = manager.summary()
    assert summary["total"] == 3
    assert summary["available"] == 3
    assert summary["selectedId"] is not None
