"""Guardrails for the plugin backend.

Two properties matter for a Decky plugin and are easy to lose by accident:

1. **The backend must run on the Python Decky bundles (3.11).** Syntax from a
   newer Python would only fail on the device, so every backend file is parsed
   with a 3.11 grammar here.
2. **The backend must be stdlib-only.** Decky cannot install packages into a
   plugin, so a stray third-party import would be an import error on device.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

# ``decky`` is injected into the plugin process by Decky Loader itself.
ALLOWED_NON_STDLIB = {"azeroth_addons", "decky"}
TARGET_PYTHON = (3, 11)


def _backend_sources() -> list[Path]:
    return sorted(BACKEND_DIR.rglob("*.py"))


def _all_sources() -> list[Path]:
    return [*_backend_sources(), REPO_ROOT / "main.py"]


def test_backend_has_sources():
    assert len(_backend_sources()) > 15


@pytest.mark.parametrize("path", _all_sources(), ids=lambda path: str(path.name))
def test_parses_under_the_plugin_python_version(path: Path):
    """Every file must be valid Python 3.11 - that is what Decky runs."""
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=TARGET_PYTHON)
    except SyntaxError as exc:  # pragma: no cover - only on regression
        pytest.fail(f"{path} is not valid Python {TARGET_PYTHON[0]}.{TARGET_PYTHON[1]}: {exc}")


def test_backend_is_stdlib_only():
    stdlib = set(sys.stdlib_module_names)
    offenders: list[tuple[str, str]] = []
    for path in _all_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib and top not in ALLOWED_NON_STDLIB:
                        offenders.append((path.name, alias.name))
            elif isinstance(node, ast.ImportFrom) and not node.level:
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib and top not in ALLOWED_NON_STDLIB:
                    offenders.append((path.name, node.module or ""))
    assert not offenders, f"third-party imports found: {offenders}"


def test_frontend_never_shells_out_to_the_engine():
    """The frontend must not know engine CLI syntax or provider endpoints.

    Prose in comments may discuss the engine; what this guards against is the
    frontend *depending* on CLI flags, subprocesses or provider URLs.
    """
    src = REPO_ROOT / "src"
    forbidden = (
        "subprocess",
        "spawn(",
        "exec(",
        "instawow install",
        "instawow update",
        "instawow remove",
        '"instawow"',
        "--profile",
        "api.curseforge.com",
        "addons.wago.io",
        "api.github.com",
        "api.tukui.org",
    )
    offenders: list[tuple[str, str]] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append((path.name, needle))
    assert not offenders, f"frontend leaks backend details: {offenders}"


def test_plugin_manifest_matches_the_plugin_directory():
    import json

    manifest = json.loads((REPO_ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["api_version"] == 1
    # The plugin runs as the deck user on purpose: it only touches the user's
    # own addon folders, so it must never ask Decky for root.
    assert "root" not in manifest.get("flags", [])
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "azeroth-addons"
