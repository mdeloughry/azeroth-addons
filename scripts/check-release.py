#!/usr/bin/env python3
"""Validate versions and extract this release's changelog without importing the app."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


def check(root: Path, tag: str | None = None) -> tuple[str, str]:
    version = json.loads((root / "package.json").read_text())["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("package.json must contain a valid release version")
    tree = ast.parse((root / "backend/azeroth_addons/__init__.py").read_text())
    backend = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    if backend != version:
        raise ValueError("Frontend and backend versions differ")
    if tag is not None and tag != f"v{version}":
        raise ValueError("Release tag must match frontend and backend versions")
    changelog = (root / "CHANGELOG.md").read_text()
    match = re.search(rf"^## {re.escape(version)}(?:\s+—[^\n]*)?\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    if not match or not match.group(1).strip():
        raise ValueError("This version needs a CHANGELOG.md entry")
    return version, match.group(1).strip() + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    try:
        version, notes = check(Path(__file__).resolve().parent.parent, args.tag)
    except (ValueError, KeyError, StopIteration) as error:
        parser.exit(1, f"Release validation failed: {error}\n")
    if args.notes:
        args.notes.write_text(notes)
    print(f"Release {version} versions and notes verified")
