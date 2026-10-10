from __future__ import annotations

from pathlib import Path

from conftest import make_version_dir, make_wow_root

from azeroth_addons.installations.discovery import (
    DiscoveryEnvironment,
    compatdata_drive_c_roots,
    default_environment,
    discover,
    discover_path,
    parse_library_folders,
    quick_pick_locations,
    scan_root,
    steam_libraries,
)


def _by_flavour(items) -> dict[str, str]:
    return {item.flavour: item.root_path for item in items}


def test_multi_version_root_expands_to_one_installation_per_version(tmp_path: Path):
    root = make_wow_root(tmp_path)
    found = scan_root(root)
    assert len(found) == 3
    flavours = {item.flavour for item in found}
    assert flavours == {"retail", "classic-era", "forever"}
    for item in found:
        assert Path(item.root_path).parent == root


def test_custom_wow_root_name_is_detected(tmp_path: Path):
    root = make_wow_root(tmp_path, folders=("_retail_",), name="World of Warcraft Public Test")
    found = scan_root(root)
    assert [item.flavour for item in found] == ["retail"]


def test_scan_root_on_a_version_directory_directly(tmp_path: Path):
    root = make_wow_root(tmp_path, folders=("_classic_era_",))
    version = root / "_classic_era_"
    found = scan_root(version)
    assert len(found) == 1
    assert found[0].flavour == "classic-era"
    assert found[0].root_path == str(version)


def test_multiple_roots_keep_multiple_copies_of_the_same_flavour(tmp_path: Path):
    internal = make_wow_root(tmp_path, folders=("_retail_",), name="World of Warcraft")
    external = make_wow_root(tmp_path / "sdcard", folders=("_retail_",), name="World of Warcraft")
    env = DiscoveryEnvironment(home=tmp_path, scan_roots=(tmp_path,))
    found = discover(env)
    retail_paths = {item.root_path for item in found}
    assert str(internal / "_retail_") in retail_paths
    assert str(external / "_retail_") in retail_paths
    assert len(retail_paths) == 2


def test_discover_deduplicates_the_same_path(tmp_path: Path):
    root = make_wow_root(tmp_path)
    env = DiscoveryEnvironment(home=tmp_path, scan_roots=(tmp_path, root))
    found = discover(env)
    assert len(found) == 3


def test_library_folders_vdf_is_parsed(tmp_path: Path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    other = tmp_path / "second-library"
    other.mkdir()
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n'
        '\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n'
        '\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n'
        '\t"2"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n'
        "}\n" % (steam, other, tmp_path / "missing-library"),
        encoding="utf-8",
    )
    folders = parse_library_folders(steam)
    assert steam in folders
    assert other in folders
    assert tmp_path / "missing-library" not in folders  # nonexistent paths are skipped


def test_steam_libraries_includes_the_root_and_listed_folders(tmp_path: Path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    other = tmp_path / "second-library"
    other.mkdir()
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{other}"\n\t}}\n}}\n',
        encoding="utf-8",
    )
    libraries = steam_libraries([steam])
    assert steam in libraries
    assert other in libraries


def test_compatdata_prefixes_are_discovered(tmp_path: Path):
    library = tmp_path / "Steam"
    drive_c = library / "steamapps" / "compatdata" / "413150" / "pfx" / "drive_c"
    wow = drive_c / "Program Files (x86)" / "World of Warcraft"
    make_version_dir(wow, "_retail_")
    make_version_dir(wow, "_classic_era_")

    roots = compatdata_drive_c_roots([library])
    assert roots == [drive_c]

    found = scan_root(drive_c)
    assert _by_flavour(found).keys() == {"retail", "classic-era"}
    for item in found:
        assert "/pfx/drive_c/" in item.root_path


def test_compatdata_prefix_with_a_nonstandard_install_path(tmp_path: Path):
    library = tmp_path / "Steam"
    drive_c = library / "steamapps" / "compatdata" / "1234" / "pfx" / "drive_c"
    # Installed under a custom folder rather than Program Files.
    wow = drive_c / "Games" / "World of Warcraft"
    make_version_dir(wow, "_retail_")
    found = scan_root(drive_c)
    assert [item.flavour for item in found] == ["retail"]


def test_scan_root_ignores_windows_system_directories(tmp_path: Path):
    drive_c = tmp_path / "drive_c"
    (drive_c / "windows" / "system32").mkdir(parents=True)
    # A decoy that must not be mistaken for a WoW install.
    decoy = drive_c / "windows" / "World of Warcraft"
    make_version_dir(decoy, "_retail_")
    assert scan_root(drive_c) == []


def test_discover_path_on_a_single_version_directory(installation):
    found = discover_path(installation.root_path)
    assert len(found) == 1
    assert found[0].flavour == "retail"


def test_discover_path_on_a_root_with_versions(wow_root: Path):
    found = discover_path(wow_root)
    assert {item.flavour for item in found} == {"retail", "classic-era", "forever"}


def test_discover_path_on_a_non_wow_directory_is_empty(tmp_path: Path):
    plain = tmp_path / "not-wow"
    plain.mkdir()
    (plain / "readme.txt").write_text("nothing here")
    assert discover_path(plain) == []


def test_quick_pick_locations_includes_home(tmp_path: Path):
    env = DiscoveryEnvironment(home=tmp_path, scan_roots=())
    picks = quick_pick_locations(env)
    paths = {pick["path"] for pick in picks}
    assert str(tmp_path) in paths


def test_default_environment_collects_removable_media_roots(tmp_path: Path, monkeypatch):
    """Removable media and Lutris-style prefixes become scan roots."""
    games = tmp_path / "Games"
    games.mkdir()
    env = default_environment({"HOME": str(tmp_path)})
    assert games in {Path(root) for root in env.scan_roots}
