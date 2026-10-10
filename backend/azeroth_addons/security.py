"""Path safety.

Every destructive filesystem operation in Azeroth Addons goes through here first.

The rules (from the project's security requirements):
* canonicalise before acting, so symlinks cannot escape the installation;
* the only valid addon target is ``<validated WoW root>/Interface/AddOns``;
* refuse protected system locations (``/``, ``/home``, ``/etc``, ...);
* if we ever extract an archive ourselves, enforce traversal/size limits.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import (
    FILESYSTEM_ERROR,
    INVALID_WOW_PATH,
    SECURITY_VIOLATION,
    AzerothAddonsError,
)

# Exact paths that may never become an addon target.
PROTECTED_ROOTS = frozenset(
    {
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/home",
        "/lib",
        "/lib64",
        "/media",
        "/mnt",
        "/opt",
        "/proc",
        "/root",
        "/run",
        "/sbin",
        "/srv",
        "/sys",
        "/tmp",
        "/usr",
        "/var",
    }
)

def _resolved_protected_roots() -> frozenset[str]:
    """Protected roots plus their symlink-resolved forms.

    Callers hand us paths in both lexical and canonical form (``/etc`` and
    ``/private/etc`` on macOS, or an automounted ``/home``), so both spellings
    must be recognised.
    """
    resolved = set(PROTECTED_ROOTS)
    for root in PROTECTED_ROOTS:
        try:
            resolved.add(str(Path(root).resolve(strict=False)))
        except OSError:  # pragma: no cover - defensive
            continue
    return frozenset(resolved)


PROTECTED_ANY = _resolved_protected_roots()

# Markers that identify a directory as a WoW *version* directory.
VERSION_MARKERS = ("Interface", "WTF", "Data", "Wow.exe", "WowClassic.exe", ".build.info")

ADDON_DIR_NAME = "AddOns"
INTERFACE_DIR_NAME = "Interface"

# Guardrails for any archive we handle ourselves (instawow extracts its own
# downloads, but these are enforced if that ever changes).
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000


def canonical(path: str | os.PathLike[str]) -> Path:
    """Resolve a path to an absolute, symlink-free form without requiring existence."""
    return Path(path).expanduser().resolve(strict=False)


def home_dir() -> Path:
    return Path(os.path.expanduser("~"))


def is_protected(path: str | os.PathLike[str]) -> bool:
    """True when the path is a protected system location (or its root anchor).

    Both the lexical path and the symlink-resolved path are checked: on some
    systems (``/etc`` on macOS, ``/home`` automounts) the two differ.
    """
    expanded = Path(path).expanduser()
    lexical = expanded if expanded.is_absolute() else Path(os.path.abspath(str(expanded)))
    candidates = {str(lexical), str(canonical(path))}
    for candidate in candidates:
        if candidate in PROTECTED_ANY:
            return True
        # Refuse a filesystem anchor (e.g. "/").
        if Path(candidate) == Path(Path(candidate).anchor):
            return True
    if str(home_dir()) in candidates:
        return True
    return False


def ensure_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> Path:
    """Return the canonical child, or raise if it is not inside the canonical parent."""
    child_path = canonical(child)
    parent_path = canonical(parent)
    if child_path == parent_path:
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Refusing to operate on the installation root itself.",
            details=f"child={child_path} parent={parent_path}",
        )
    if not child_path.is_relative_to(parent_path):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Refusing to operate outside the installation directory.",
            details=f"child={child_path} parent={parent_path}",
        )
    return child_path


def looks_like_version_dir(path: str | os.PathLike[str]) -> bool:
    """A WoW version directory contains at least one recognised marker."""
    target = canonical(path)
    if not target.is_dir():
        return False
    return any((target / marker).exists() for marker in VERSION_MARKERS)


def looks_like_wow_root(path: str | os.PathLike[str]) -> bool:
    """A WoW root either is a version directory or contains version subdirectories."""
    target = canonical(path)
    if looks_like_version_dir(target):
        return True
    if not target.is_dir():
        return False
    from .installations.flavours import is_version_folder  # local import: avoid cycle

    try:
        entries = os.scandir(target)
    except OSError:
        return False
    with entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            # The subdirectory must be named like a version *and* carry markers:
            # an empty ``_retail_`` folder is not an installation.
            if is_version_folder(entry.name) and looks_like_version_dir(entry.path):
                return True
    return False


def validate_installation_root(root: str | os.PathLike[str]) -> Path:
    """Validate a candidate installation root before it is registered."""
    # Check protection on the path as given: canonicalising can hide the
    # lexical spelling ("/etc" -> "/private/etc").
    if is_protected(root):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "That location is not a valid World of Warcraft installation.",
            details=f"path={root}",
        )

    root_path = canonical(root)
    if not root_path.exists():
        raise AzerothAddonsError(
            INVALID_WOW_PATH,
            "That folder does not exist.",
            details=f"path={root_path}",
        )
    if not root_path.is_dir():
        raise AzerothAddonsError(
            INVALID_WOW_PATH,
            "That path is not a folder.",
            details=f"path={root_path}",
        )
    if is_protected(root_path):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "That location is not a valid World of Warcraft installation.",
            details=f"path={root_path}",
        )
    if not looks_like_wow_root(root_path):
        raise AzerothAddonsError(
            INVALID_WOW_PATH,
            "That folder does not look like a World of Warcraft installation.",
            details=f"path={root_path}",
        )
    return root_path


def addons_path_for(root: str | os.PathLike[str]) -> Path:
    return canonical(root) / INTERFACE_DIR_NAME / ADDON_DIR_NAME


def validate_addons_target(
    addons_path: str | os.PathLike[str],
    installation_root: str | os.PathLike[str],
) -> Path:
    """Validate the exact directory an addon operation will write to.

    Order matters, so the caller gets the most useful error:

    1. the path as written must *look* like ``.../Interface/AddOns``;
    2. after resolving symlinks it must still look like that, otherwise a
       symlink redirected us somewhere else;
    3. it must stay inside the installation;
    4. neither the root nor the target may be a protected location.

    Returns the canonical AddOns path.
    """
    lexical = Path(str(addons_path)).expanduser()
    if not lexical.is_absolute():
        lexical = Path(os.path.abspath(str(lexical)))

    if lexical.name != ADDON_DIR_NAME or lexical.parent.name != INTERFACE_DIR_NAME:
        raise AzerothAddonsError(
            INVALID_WOW_PATH,
            "Addon operations must target an Interface/AddOns directory.",
            details=f"path={lexical}",
        )

    target = canonical(addons_path)
    if target.name != ADDON_DIR_NAME or target.parent.name != INTERFACE_DIR_NAME:
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "That addon folder resolves outside the installation.",
            details=f"path={lexical} resolved={target}",
        )

    root_path = canonical(installation_root)

    if is_protected(installation_root) or is_protected(root_path):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Refusing to modify that location.",
            details=f"root={root_path}",
        )

    ensure_within(target, root_path)

    if is_protected(target):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Refusing to modify that location.",
            details=f"path={target}",
        )

    return target


def validate_archive_member(name: str) -> str:
    """Reject archive members that would escape the extraction root."""
    if not name:
        raise AzerothAddonsError(SECURITY_VIOLATION, "Archive contains an unnamed entry.")

    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or normalised.startswith("~"):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive contains an absolute path.",
            details=f"member={name}",
        )
    # Windows drive letters and UNC paths.
    if len(normalised) >= 2 and normalised[1] == ":":
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive contains a drive-qualified path.",
            details=f"member={name}",
        )
    if normalised.startswith("//"):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive contains a UNC path.",
            details=f"member={name}",
        )

    parts = [part for part in normalised.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive contains a path traversal entry.",
            details=f"member={name}",
        )
    return "/".join(parts)


def validate_extraction_destination(
    destination: str | os.PathLike[str],
    installation_root: str | os.PathLike[str],
) -> Path:
    """Validate where an archive would be extracted to."""
    dest = canonical(destination)
    root = canonical(installation_root)
    if is_protected(dest):
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Refusing to extract into that location.",
            details=f"path={dest}",
        )
    ensure_within(dest, root)
    return dest


def validate_archive_limits(total_bytes: int, member_count: int) -> None:
    """Reject archives that exceed the configured safety limits."""
    if total_bytes > MAX_ARCHIVE_BYTES:
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive is too large to process safely.",
            details=f"bytes={total_bytes} limit={MAX_ARCHIVE_BYTES}",
        )
    if member_count > MAX_ARCHIVE_MEMBERS:
        raise AzerothAddonsError(
            SECURITY_VIOLATION,
            "Archive contains too many files to process safely.",
            details=f"members={member_count} limit={MAX_ARCHIVE_MEMBERS}",
        )


def check_writable(path: str | os.PathLike[str]) -> None:
    """Raise a structured error if the directory cannot be written to."""
    target = canonical(path)
    if not target.exists():
        raise AzerothAddonsError(
            FILESYSTEM_ERROR,
            "That folder is not available.",
            details=f"path={target}",
        )
    if not os.access(target, os.W_OK):
        raise AzerothAddonsError(
            FILESYSTEM_ERROR,
            "That folder is not writable.",
            details=f"path={target}",
        )
