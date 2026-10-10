from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import make_version_dir

from azeroth_addons import security
from azeroth_addons.errors import (
    FILESYSTEM_ERROR,
    INVALID_WOW_PATH,
    SECURITY_VIOLATION,
    AzerothAddonsError,
)


def test_canonical_resolves_symlinks(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert security.canonical(link) == real.resolve()


@pytest.mark.parametrize("path", ["/", "/home", "/etc", "/usr", "/boot"])
def test_protected_system_paths(path):
    assert security.is_protected(path)


def test_home_directory_itself_is_protected():
    assert security.is_protected(Path(os.path.expanduser("~")))


def test_an_installation_is_not_protected(wow_root: Path):
    assert not security.is_protected(wow_root / "_retail_")


def test_validate_installation_root_accepts_a_version_directory(wow_root: Path):
    assert security.validate_installation_root(wow_root / "_retail_") == (wow_root / "_retail_").resolve()


def test_validate_installation_root_rejects_missing_paths(tmp_path: Path):
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_installation_root(tmp_path / "nope")
    assert excinfo.value.code == INVALID_WOW_PATH


def test_validate_installation_root_rejects_protected_paths():
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_installation_root("/etc")
    assert excinfo.value.code == SECURITY_VIOLATION


def test_validate_addons_target_accepts_interface_addons(wow_root: Path):
    version = wow_root / "_retail_"
    target = security.validate_addons_target(version / "Interface" / "AddOns", version)
    assert target == (version / "Interface" / "AddOns").resolve()


def test_validate_addons_target_requires_interface_addons_shape(wow_root: Path):
    version = wow_root / "_retail_"
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_addons_target(version / "Interface", version)
    assert excinfo.value.code == INVALID_WOW_PATH


def test_validate_addons_target_rejects_traversal_outside_the_root(wow_root: Path, tmp_path: Path):
    version = wow_root / "_retail_"
    outside = tmp_path / "elsewhere" / "Interface" / "AddOns"
    outside.mkdir(parents=True)
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_addons_target(outside, version)
    assert excinfo.value.code == SECURITY_VIOLATION


def test_validate_addons_target_rejects_a_symlink_escape(wow_root: Path, tmp_path: Path):
    """A symlinked AddOns directory pointing outside the installation is refused."""
    version = wow_root / "_retail_"
    outside = tmp_path / "attacker" / "InstallTarget"
    outside.mkdir(parents=True)
    link = version / "Interface" / "AddOns"
    import shutil

    shutil.rmtree(link)
    link.symlink_to(outside)
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_addons_target(link, version)
    assert excinfo.value.code == SECURITY_VIOLATION


def test_validate_addons_target_rejects_the_installation_root_itself(wow_root: Path):
    version = wow_root / "_retail_"
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_addons_target(version, version)
    assert excinfo.value.code == INVALID_WOW_PATH


def test_ensure_within_rejects_siblings(tmp_path: Path):
    parent = tmp_path / "parent"
    sibling = tmp_path / "sibling"
    parent.mkdir()
    sibling.mkdir()
    with pytest.raises(AzerothAddonsError):
        security.ensure_within(sibling, parent)


@pytest.mark.parametrize(
    "member",
    ["/etc/passwd", "C:\\windows\\system32", "\\\\server\\share", "../escape", "a/../../b", "~/secret"],
)
def test_validate_archive_member_rejects_unsafe_paths(member):
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.validate_archive_member(member)
    assert excinfo.value.code == SECURITY_VIOLATION


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("Addon/Addon.toc", "Addon/Addon.toc"),
        ("./Addon/Addon.lua", "Addon/Addon.lua"),
        ("Addon\\sub\\File.lua", "Addon/sub/File.lua"),
    ],
)
def test_validate_archive_member_accepts_normal_paths(member, expected):
    assert security.validate_archive_member(member) == expected


def test_validate_archive_limits():
    security.validate_archive_limits(1_000, 10)
    with pytest.raises(AzerothAddonsError):
        security.validate_archive_limits(security.MAX_ARCHIVE_BYTES + 1, 1)
    with pytest.raises(AzerothAddonsError):
        security.validate_archive_limits(1, security.MAX_ARCHIVE_MEMBERS + 1)


def test_validate_extraction_destination_stays_inside_the_root(wow_root: Path, tmp_path: Path):
    version = wow_root / "_retail_"
    good = version / "Interface" / "AddOns"
    assert security.validate_extraction_destination(good, version) == good.resolve()
    with pytest.raises(AzerothAddonsError):
        security.validate_extraction_destination(tmp_path / "elsewhere", version)


def test_check_writable_reports_missing_and_unwritable(tmp_path: Path):
    with pytest.raises(AzerothAddonsError) as excinfo:
        security.check_writable(tmp_path / "missing")
    assert excinfo.value.code == FILESYSTEM_ERROR
    assert security.check_writable(tmp_path) is None


def test_looks_like_version_dir_requires_a_marker(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert not security.looks_like_version_dir(empty)
    assert security.looks_like_version_dir(make_version_dir(tmp_path, "_retail_"))
