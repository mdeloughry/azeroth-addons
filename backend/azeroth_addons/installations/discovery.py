"""Discovery of local World of Warcraft installations.

Scans, without hardcoding a single appid, prefix or Steam library:

* every Steam library listed in ``steamapps/libraryfolders.vdf``;
* every Proton prefix under each library's ``steamapps/compatdata/*/pfx``;
* removable media under ``/run/media/*/*`` and ``/mnt/*``;
* the user's ``~/Games`` (Lutris-style prefixes);
* any extra roots the caller supplies.

A ``World of Warcraft`` root may contain several version directories; each is
reported separately.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from ..logctx import get_logger
from ..security import canonical, looks_like_version_dir
from .flavours import FlavourInfo, flavour_for_folder, is_version_folder, normalise_flavour
from .models import location_label

logger = get_logger()

# Directories that are never worth walking into.
PRUNE_DIRS = frozenset(
    {
        "windows",
        "system32",
        "syswow64",
        "winsxs",
        "$recycle.bin",
        "programdata",
        "users",
        "temp",
        "tmp",
        "node_modules",
        ".git",
        ".cache",
        "shadercache",
        "downloading",
        "temp_install",
        "librarycache",
        "music",
        "videos",
        "pictures",
        "documents",
        "appdata",
        "steamapps",
        ".steam",
        "proton",
        "dist",
        # Inside a WoW version directory these hold no installations.
        "data",
        "interface",
        "wtf",
        "cache",
        "logs",
        "errors",
        "screenshots",
        "fonts",
        "indices",
        "updates",
    }
)

WOW_DIR_NAME = re.compile(r"^world of warcraft.*$", re.IGNORECASE)
_VDF_PATH = re.compile(r'"path"\s*"([^"]+)"')

# Fast paths checked inside every Proton drive_c before falling back to a walk.
KNOWN_DRIVE_C_PATHS = (
    "Program Files (x86)/World of Warcraft",
    "Program Files/World of Warcraft",
)


@dataclass(frozen=True)
class Discovered:
    root_path: str
    flavour: str
    label: str
    version_folder: str
    instawow_flavour: str | None
    product_code: str | None
    source: str = "auto"

    @property
    def location_label(self) -> str:
        return location_label(self.root_path)


@dataclass
class DiscoveryEnvironment:
    home: Path
    steam_roots: tuple[Path, ...] = ()
    scan_roots: tuple[Path, ...] = ()
    extra_roots: tuple[Path, ...] = ()
    max_depth: int = 3

    def all_scan_roots(self) -> list[Path]:
        seen: dict[str, Path] = {}
        for path in (*self.scan_roots, *self.extra_roots):
            key = str(canonical(path))
            seen.setdefault(key, canonical(path))
        return list(seen.values())


def steam_root_candidates(home: Path, env: Mapping[str, str] | None = None) -> list[Path]:
    env = env or os.environ
    xdg_data = Path(env.get("XDG_DATA_HOME") or (home / ".local" / "share"))
    candidates = [
        xdg_data / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
        home / ".local" / "share" / "Steam",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = canonical(candidate)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            out.append(resolved)
    return out


def parse_library_folders(steam_root: Path) -> list[Path]:
    """Parse ``steamapps/libraryfolders.vdf`` without a full VDF parser."""
    vdf = canonical(steam_root) / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return []
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("could not read %s: %s", vdf, exc)
        return []
    folders: list[Path] = []
    for match in _VDF_PATH.finditer(text):
        candidate = canonical(Path(match.group(1)))
        if candidate.is_dir():
            folders.append(candidate)
    return folders


def steam_libraries(steam_roots: Sequence[Path]) -> list[Path]:
    libraries: dict[str, Path] = {}
    for root in steam_roots:
        libraries.setdefault(str(canonical(root)), canonical(root))
        for folder in parse_library_folders(root):
            libraries.setdefault(str(folder), folder)
    return list(libraries.values())


def compatdata_drive_c_roots(libraries: Sequence[Path]) -> list[Path]:
    """Every readable ``.../compatdata/<appid>/pfx/drive_c`` across all libraries."""
    roots: list[Path] = []
    for library in libraries:
        compatdata = canonical(library) / "steamapps" / "compatdata"
        if not compatdata.is_dir():
            continue
        try:
            entries = sorted(os.scandir(compatdata), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            drive_c = Path(entry.path) / "pfx" / "drive_c"
            if drive_c.is_dir():
                roots.append(drive_c)
    return roots


def default_environment(env: Mapping[str, str] | None = None) -> DiscoveryEnvironment:
    env = env or os.environ
    home = Path(env.get("HOME") or os.path.expanduser("~"))
    steam_roots = tuple(steam_root_candidates(home, env))
    libraries = steam_libraries(steam_roots)

    scan_roots: list[Path] = []
    # Proton prefixes first: that is where Steam WoW installs live.
    scan_roots.extend(compatdata_drive_c_roots(libraries))
    # Removable media (SD cards, external SSDs).
    for base in (Path("/run/media"), Path("/mnt")):
        if base.is_dir():
            try:
                for entry in os.scandir(base):
                    if not entry.is_dir():
                        continue
                    if base.name == "media":
                        # /run/media/<user>/<drive>
                        try:
                            for drive in os.scandir(entry.path):
                                if drive.is_dir():
                                    scan_roots.append(Path(drive.path))
                        except OSError:
                            continue
                    else:
                        scan_roots.append(Path(entry.path))
            except OSError:
                continue
    # Lutris / manual installs.
    games = home / "Games"
    if games.is_dir():
        scan_roots.append(games)

    return DiscoveryEnvironment(
        home=home,
        steam_roots=steam_roots,
        scan_roots=tuple(scan_roots),
        extra_roots=(),
        max_depth=3,
    )


def _collect_version_dirs(directory: Path) -> list[tuple[str, Path]]:
    """If ``directory`` is a WoW root, return its version folders.

    A folder only counts when it carries the markers of a real game
    installation, so an empty ``_retail_`` directory is ignored.
    """
    found: list[tuple[str, Path]] = []
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        return found
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if is_version_folder(entry.name) and looks_like_version_dir(entry.path):
            found.append((entry.name, Path(entry.path)))
    return found


def _walk_for_roots(root: Path, max_depth: int) -> list[Path]:
    """Bounded walk returning directories that look like WoW roots."""
    roots: dict[str, Path] = {}
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if _collect_version_dirs(current):
            roots.setdefault(str(canonical(current)), canonical(current))
            continue  # never descend into a WoW root's version folders
        if depth >= max_depth:
            continue
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name.startswith(".") and entry.name not in (".local",):
                continue
            if entry.name.lower() in PRUNE_DIRS:
                continue
            if WOW_DIR_NAME.match(entry.name):
                # A directory that *looks* like WoW is worth checking directly.
                candidate = Path(entry.path)
                if _collect_version_dirs(candidate):
                    roots.setdefault(str(canonical(candidate)), canonical(candidate))
                    continue
            stack.append((Path(entry.path), depth + 1))
    return list(roots.values())


def _version_dir_candidates(root: Path) -> list[tuple[str, Path]]:
    results = _collect_version_dirs(root)
    if results:
        return results
    # The user may have pointed straight at a version directory.
    if looks_like_version_dir(root):
        return [(root.name, root)]
    return []


def scan_root(root: Path, max_depth: int = 3) -> list[Discovered]:
    """Find every installation reachable from a single scan root."""
    root = canonical(root)
    if not root.is_dir():
        return []

    discovered: list[Discovered] = []

    # Fast path for Proton prefixes.
    if root.name == "drive_c":
        for relative in KNOWN_DRIVE_C_PATHS:
            candidate = root / relative
            if candidate.is_dir():
                discovered.extend(_discover_in_root(candidate))

    for wow_root in _walk_for_roots(root, max_depth):
        found_here = _discover_in_root(wow_root)
        if not found_here and wow_root == root:
            continue
        discovered.extend(found_here)

    # A scan root that *is* a version directory.
    if looks_like_version_dir(root):
        discovered.extend(_discovered_entries(root.name, root))

    deduped: dict[str, Discovered] = {}
    for item in discovered:
        deduped.setdefault(str(canonical(item.root_path)), item)
    return list(deduped.values())


def _discover_in_root(wow_root: Path) -> list[Discovered]:
    entries = _version_dir_candidates(wow_root)
    out: list[Discovered] = []
    for folder, path in entries:
        out.extend(_discovered_entries(folder, path))
    return out


def _discovered_entries(folder: str, path: Path) -> list[Discovered]:
    info: FlavourInfo | None = flavour_for_folder(folder)
    if info is None:
        return [
            Discovered(
                root_path=str(canonical(path)),
                flavour=normalise_flavour(None),
                label="Unknown",
                version_folder=folder,
                instawow_flavour=None,
                product_code=None,
            )
        ]
    return [
        Discovered(
            root_path=str(canonical(path)),
            flavour=info.flavour,
            label=info.label,
            version_folder=info.folder,
            instawow_flavour=info.instawow_flavour,
            product_code=info.product_code,
        )
    ]


def discover(env: DiscoveryEnvironment | None = None) -> list[Discovered]:
    """Discover every installation reachable from the environment."""
    env = env or default_environment()
    found: dict[str, Discovered] = {}
    for root in env.all_scan_roots():
        for item in scan_root(root, env.max_depth):
            key = str(canonical(item.root_path))
            found.setdefault(key, item)
    return sorted(found.values(), key=lambda item: (item.flavour, item.root_path))


def discover_path(path: str | os.PathLike[str]) -> list[Discovered]:
    """Discover installations inside one user-supplied path."""
    root = canonical(path)
    if not root.exists():
        return []
    # Pointing straight at a version directory is the most precise case.
    if looks_like_version_dir(root):
        return _discovered_entries(root.name, root)
    return scan_root(root, max_depth=2)


def quick_pick_locations(env: DiscoveryEnvironment | None = None) -> list[dict[str, str]]:
    """Controller-friendly starting points for the folder picker."""
    env = env or default_environment()
    picks: list[dict[str, str]] = [{"label": "Home", "path": str(env.home)}]
    for root in env.steam_roots:
        picks.append({"label": f"Steam ({root.name})", "path": str(root)})
    libraries = steam_libraries(env.steam_roots)
    for library in libraries:
        picks.append({"label": "Steam library", "path": str(library / "steamapps" / "common")})
    for base in (Path("/run/media"), Path("/mnt")):
        if base.is_dir():
            picks.append({"label": str(base), "path": str(base)})
    games = env.home / "Games"
    if games.is_dir():
        picks.append({"label": "Games", "path": str(games)})

    deduped: dict[str, dict[str, str]] = {}
    for pick in picks:
        deduped.setdefault(pick["path"], pick)
    return list(deduped.values())


def iter_scan_roots(env: DiscoveryEnvironment) -> Iterable[str]:
    for root in env.all_scan_roots():
        yield str(root)
