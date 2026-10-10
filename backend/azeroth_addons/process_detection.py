"""Per-installation WoW running detection.

Detection is per installation, not global: Retail running must not block
Classic Era operations. We scan ``/proc`` for processes whose command line,
executable or working directory references the installation.

Matching handles both native Linux paths and Proton/Wine Windows paths
(``C:\\Program Files (x86)\\World of Warcraft\\_retail_``) by deriving needles
from the installation's canonical root.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from .security import canonical

_PROC_NAME = re.compile(r"^\d+$")
_DRIVE_C = re.compile(r"/pfx/drive_c/(?P<tail>.*)$")


def _normalise(text: str) -> str:
    return text.replace("\\", "/").replace("\x00", " ").lower()


def _read_text(path: Path, limit: int = 8192) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def installation_needles(installation_root: str) -> tuple[str, ...]:
    """Substrings that identify the installation inside a process listing.

    Only specific needles are used (the full Linux path, the Windows path, and
    the prefix-relative path). A bare ``_retail_`` would match unrelated
    processes and cause false "game is running" blocks.
    """
    root = canonical(installation_root)
    text = str(root)
    needles: set[str] = {_normalise(text)}

    match = _DRIVE_C.search(text)
    if match:
        tail = match.group("tail")
        needles.add(_normalise(f"c:/{tail}"))
        needles.add(_normalise(f"c:\\{tail}"))
        # Some Proton builds expose the path without the drive_c anchor.
        needles.add(_normalise(tail))

    return tuple(needle for needle in needles if len(needle) > 3)


def _readlink(path: Path) -> str:
    """Resolve a /proc symlink, tolerating anything we are not allowed to read."""
    try:
        return os.readlink(path)
    except OSError:
        # EACCES for processes owned by another user (PID 1, system daemons),
        # EINVAL when the entry is not a symlink, ENOENT when it just exited.
        return ""


def iter_process_strings(proc_root: str | os.PathLike[str] = "/proc") -> Iterator[str]:
    """Yield the command line / exe / cwd of every process we can read.

    The scan must never raise: the process table contains entries owned by
    other users, and a failure here would take down every addon operation
    (the running-game gate calls this).
    """
    pids: list[str] = []
    try:
        with os.scandir(proc_root) as scandir:
            for entry in scandir:
                try:
                    if _PROC_NAME.match(entry.name) and entry.is_dir():
                        pids.append(entry.path)
                except OSError:
                    continue
    except OSError:
        return

    for pid_path in pids:
        pid_dir = Path(pid_path)
        try:
            cmdline = _read_text(pid_dir / "cmdline")
            if cmdline:
                yield cmdline
            cwd = _readlink(pid_dir / "cwd")
            if cwd:
                yield cwd
            exe = _readlink(pid_dir / "exe")
            if exe:
                yield exe
        except OSError:  # pragma: no cover - defensive: the process vanished mid-scan
            continue


def running_installation_ids(
    installations: Iterable[Any],
    proc_root: str | os.PathLike[str] = "/proc",
) -> set[str]:
    """Return the ids of installations that appear to be running."""
    candidates = [inst for inst in installations if getattr(inst, "root_path", None)]
    if not candidates:
        return set()

    needles: dict[str, tuple[str, ...]] = {
        inst.id: installation_needles(inst.root_path) for inst in candidates
    }
    haystack = " \n".join(_normalise(text) for text in iter_process_strings(proc_root))

    running: set[str] = set()
    if not haystack:
        return running
    for installation_id, inst_needles in needles.items():
        if any(needle in haystack for needle in inst_needles):
            running.add(installation_id)
    return running


def is_installation_running(
    installation: Any,
    proc_root: str | os.PathLike[str] = "/proc",
) -> bool:
    return installation.id in running_installation_ids([installation], proc_root)


def describe_running(installations: Iterable[Any]) -> list[dict[str, Any]]:
    """UI-friendly summary used by the status payloads."""
    installations = list(installations)
    running = running_installation_ids(installations)
    return [
        {"id": inst.id, "displayName": inst.display_name, "running": inst.id in running}
        for inst in installations
    ]
