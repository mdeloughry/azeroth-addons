"""World of Warcraft flavour vocabulary.

Two vocabularies exist and must not be confused:

* **ours** - a small, stable set used by the UI and the domain model:
  ``retail``, ``classic-era``, ``forever``, ``classic``, ``unknown``.
* **instawow's** - the engine-facing flavour name (``mainline``,
  ``vanilla_classic``, ``forever_classic``, ``mists_classic``, ...) that is
  written into the per-installation engine profile.

Version directories are identified by their ``_folder_`` name, which is how
Blizzard lays out a multi-version WoW root.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlavourInfo:
    flavour: str
    label: str
    instawow_flavour: str | None
    product_code: str | None
    folder: str


VERSION_FOLDERS: dict[str, FlavourInfo] = {
    "_retail_": FlavourInfo("retail", "Retail", "mainline", "wow", "_retail_"),
    "_classic_era_": FlavourInfo("classic-era", "Classic Era", "vanilla_classic", "wow_classic_era", "_classic_era_"),
    # WoW Forever. instawow maps the wow_classic_beta product onto forever_classic.
    "_classic_beta_": FlavourInfo("forever", "Forever", "forever_classic", "wow_classic_beta", "_classic_beta_"),
    "_classic_": FlavourInfo("classic", "Classic", "mists_classic", "wow_classic", "_classic_"),
    "_anniversary_": FlavourInfo("classic", "Classic (Anniversary)", "tbc_classic", "wow_anniversary", "_anniversary_"),
    # Test realms: recognised so discovery can see them, but flavour is unknown
    # so users never install into a PTR by accident.
    "_ptr_": FlavourInfo("unknown", "Public Test Realm", None, "wow", "_ptr_"),
    "_xptr_": FlavourInfo("unknown", "Public Test Realm (Beta)", None, "wow", "_xptr_"),
    "_classic_era_ptr_": FlavourInfo("unknown", "Classic Era PTR", None, "wow_classic_era", "_classic_era_ptr_"),
    "_classic_ptr_": FlavourInfo("unknown", "Classic PTR", None, "wow_classic", "_classic_ptr_"),
}

FLAVOUR_ORDER = ("retail", "classic-era", "forever", "classic", "unknown")

FLAVOUR_LABELS = {
    "retail": "Retail",
    "classic-era": "Classic Era",
    "forever": "Forever",
    "classic": "Classic",
    "unknown": "Unknown",
}

# Legacy/external spelling accepted from persisted state or callers.
_FLAVOUR_ALIASES = {
    "mainline": "retail",
    "retail": "retail",
    "vanilla_classic": "classic-era",
    "classic_era": "classic-era",
    "era": "classic-era",
    "classic-era": "classic-era",
    "forever_classic": "forever",
    "forever": "forever",
    "mists_classic": "classic",
    "tbc_classic": "classic",
    "wrath_classic": "classic",
    "cata_classic": "classic",
    "classic": "classic",
    "unknown": "unknown",
}


def normalise_flavour(value: str | None) -> str:
    if not value:
        return "unknown"
    return _FLAVOUR_ALIASES.get(value.lower(), "unknown")


def is_version_folder(name: str) -> bool:
    return name.lower() in VERSION_FOLDERS


def flavour_for_folder(name: str) -> FlavourInfo | None:
    return VERSION_FOLDERS.get(name.lower())


def flavour_label(flavour: str) -> str:
    return FLAVOUR_LABELS.get(flavour, "Unknown")


def instawow_flavour_for(folder_name: str | None, fallback: str | None = None) -> str | None:
    """Engine-facing flavour for a version folder, with a graceful fallback."""
    if folder_name:
        info = flavour_for_folder(folder_name)
        if info and info.instawow_flavour:
            return info.instawow_flavour
    if fallback:
        info = VERSION_FOLDERS.get(fallback.lower())
        if info and info.instawow_flavour:
            return info.instawow_flavour
    return None
