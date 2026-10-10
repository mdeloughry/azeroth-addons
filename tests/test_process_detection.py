from __future__ import annotations

from pathlib import Path

from conftest import make_version_dir

from azeroth_addons.installations.models import WowInstallation
from azeroth_addons.process_detection import (
    describe_running,
    installation_needles,
    is_installation_running,
    running_installation_ids,
)


def _installation(root: Path, flavour: str = "retail", folder: str = "_retail_") -> WowInstallation:
    return WowInstallation.create(
        root_path=str(root),
        flavour=flavour,
        display_name=f"{flavour} - Test",
        version_folder=folder,
        instawow_flavour="mainline",
    )


def test_needles_include_linux_and_windows_forms(tmp_path: Path):
    drive_c = tmp_path / "pfx" / "drive_c"
    version = drive_c / "Program Files (x86)" / "World of Warcraft" / "_retail_"
    version.mkdir(parents=True)
    needles = installation_needles(str(version))
    assert any("program files (x86)/world of warcraft/_retail_" in needle for needle in needles)
    assert any(needle.startswith("c:/") for needle in needles)


def test_native_linux_install_is_detected(tmp_path: Path):
    version = make_version_dir(tmp_path / "World of Warcraft", "_retail_")
    installation = _installation(version)
    proc, add = _add_process(tmp_path)
    add(100, f"/usr/bin/wow-runner{NUL}--path={version}/Wow.exe{NUL}")
    assert is_installation_running(installation, proc)
    assert running_installation_ids([installation], proc) == {installation.id}


def test_proton_windows_path_is_detected(tmp_path: Path):
    drive_c = tmp_path / "compatdata" / "42" / "pfx" / "drive_c"
    version = drive_c / "Program Files (x86)" / "World of Warcraft" / "_retail_"
    version.mkdir(parents=True)
    (version / "Wow.exe").write_bytes(b"")
    installation = _installation(version)

    proc, add = _add_process(tmp_path)
    add(
        200,
        "Z:\\home\\deck\\wine\\wow.exe{NUL}-launcher"
        "C:\\Program Files (x86)\\World of Warcraft\\_retail_\\Wow.exe{NUL}",
    )
    assert is_installation_running(installation, proc)


def test_retail_running_does_not_block_classic_era(tmp_path: Path):
    root = tmp_path / "World of Warcraft"
    retail = make_version_dir(root, "_retail_")
    era = make_version_dir(root, "_classic_era_")
    retail_inst = _installation(retail, "retail", "_retail_")
    era_inst = _installation(era, "classic-era", "_classic_era_")

    proc, add = _add_process(tmp_path)
    add(300, f"/usr/bin/wine{NUL}{retail}/Wow.exe{NUL}")

    assert running_installation_ids([retail_inst, era_inst], proc) == {retail_inst.id}
    assert is_installation_running(retail_inst, proc) is True
    assert is_installation_running(era_inst, proc) is False


def test_unrelated_processes_do_not_match(tmp_path: Path):
    version = make_version_dir(tmp_path / "World of Warcraft", "_retail_")
    installation = _installation(version)
    proc, add = _add_process(tmp_path)
    add(400, "/usr/bin/firefox{NUL}https://example.com{NUL}")
    add(401, "/usr/bin/steam{NUL}-silent{NUL}")
    assert running_installation_ids([installation], proc) == set()


def test_missing_proc_root_is_safe(tmp_path: Path):
    version = make_version_dir(tmp_path / "World of Warcraft", "_retail_")
    installation = _installation(version)
    assert running_installation_ids([installation], tmp_path / "no-proc") == set()


def test_describe_running_summarises_state(tmp_path: Path):
    version = make_version_dir(tmp_path / "World of Warcraft", "_retail_")
    installation = _installation(version)
    described = describe_running([installation])
    assert set(described[0]) == {"id", "displayName", "running"}
    assert described[0]["id"] == installation.id


# --- helpers ---------------------------------------------------------------


class _ProcBuilder:
    def __init__(self, proc_root: Path) -> None:
        self.proc_root = proc_root

    def __call__(self, pid: int, cmdline: str) -> None:
        pid_dir = self.proc_root / str(pid)
        pid_dir.mkdir(parents=True, exist_ok=True)
        (pid_dir / "cmdline").write_bytes(cmdline.replace("{NUL}", "\x00").encode("utf-8"))


NUL = "{NUL}"


def _add_process(tmp_path: Path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir(exist_ok=True)
    return proc_root, _ProcBuilder(proc_root)
