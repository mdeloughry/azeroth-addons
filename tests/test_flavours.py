from __future__ import annotations

import pytest

from azeroth_addons.installations import flavours


@pytest.mark.parametrize(
    ("folder", "flavour", "label", "instawow", "product"),
    [
        ("_retail_", "retail", "Retail", "mainline", "wow"),
        ("_classic_era_", "classic-era", "Classic Era", "vanilla_classic", "wow_classic_era"),
        ("_classic_beta_", "forever", "Forever", "forever_classic", "wow_classic_beta"),
        ("_classic_", "classic", "Classic", "mists_classic", "wow_classic"),
        ("_anniversary_", "classic", "Classic (Anniversary)", "tbc_classic", "wow_anniversary"),
    ],
)
def test_known_version_folders(folder, flavour, label, instawow, product):
    info = flavours.flavour_for_folder(folder)
    assert info is not None
    assert (info.flavour, info.label, info.instawow_flavour, info.product_code) == (
        flavour,
        label,
        instawow,
        product,
    )


def test_is_version_folder_is_case_insensitive():
    assert flavours.is_version_folder("_RETAIL_")
    assert not flavours.is_version_folder("_unknown_")
    assert not flavours.is_version_folder("Interface")


def test_forever_maps_to_instawow_forever_classic():
    """'Forever' is the WoW Forever flavour added in instawow 7.2.0."""
    assert flavours.instawow_flavour_for("_classic_beta_") == "forever_classic"


def test_ptr_folders_are_recognised_but_unknown_flavour():
    for folder in ("_ptr_", "_xptr_", "_classic_era_ptr_"):
        info = flavours.flavour_for_folder(folder)
        assert info is not None
        assert info.flavour == "unknown"
        assert info.instawow_flavour is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("mainline", "retail"),
        ("retail", "retail"),
        ("vanilla_classic", "classic-era"),
        ("forever_classic", "forever"),
        ("mists_classic", "classic"),
        ("cata_classic", "classic"),
        ("nonsense", "unknown"),
        (None, "unknown"),
    ],
)
def test_normalise_flavour_aliases(value, expected):
    assert flavours.normalise_flavour(value) == expected


def test_instawow_flavour_falls_back_to_folder_name():
    assert flavours.instawow_flavour_for(None, "_retail_") == "mainline"
    assert flavours.instawow_flavour_for(None, "unrecognised") is None
