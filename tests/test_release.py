"""Release validation must stop mismatched tags/versions and empty notes."""
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "release_check", Path(__file__).resolve().parents[1] / "scripts/check-release.py"
)
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


def release_root(tmp_path, version="0.1.8", backend="0.1.8", notes="Fixed safety gates."):
    (tmp_path / "package.json").write_text(json.dumps({"version": version}))
    backend_dir = tmp_path / "backend/azeroth_addons"
    backend_dir.mkdir(parents=True)
    (backend_dir / "__init__.py").write_text(f'__version__ = "{backend}"\n')
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {version}\n\n{notes}\n\n## 0.1.7\n\nOlder release.\n"
    )
    return tmp_path


def test_extracts_only_current_notes(tmp_path):
    root = release_root(tmp_path)
    assert release_check.check(root, "v0.1.8") == ("0.1.8", "Fixed safety gates.\n")


@pytest.mark.parametrize("tag", ["v0.1.7", "0.1.8", "main"])
def test_rejects_wrong_tag(tmp_path, tag):
    with pytest.raises(ValueError, match="tag must match"):
        release_check.check(release_root(tmp_path), tag)


def test_rejects_different_backend_version(tmp_path):
    with pytest.raises(ValueError, match="versions differ"):
        release_check.check(release_root(tmp_path, backend="0.1.7"))


@pytest.mark.parametrize("changelog", ["# Changelog\n", "## 0.1.8\n\n## 0.1.7\nOld notes\n"])
def test_requires_nonempty_current_notes(tmp_path, changelog):
    root = release_root(tmp_path)
    (root / "CHANGELOG.md").write_text(changelog)
    with pytest.raises(ValueError, match="CHANGELOG"):
        release_check.check(root)


def test_accepts_explicit_prerelease_tag(tmp_path):
    root = release_root(tmp_path, version="0.1.9-beta.1", backend="0.1.9-beta.1")
    assert release_check.check(root, "v0.1.9-beta.1")[0] == "0.1.9-beta.1"
