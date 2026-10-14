"""GitHub release discovery. Installation is delegated to Decky's installer."""
from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request
from typing import Any

from . import __version__
from .errors import INVALID_ARGUMENT, NOT_READY, AzerothAddonsError
from .networking import create_ssl_context
from .settings import SettingsStore

REPOSITORY = "mdeloughry/azeroth-addons"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_URL = f"{RELEASES_URL}/latest/download/azeroth-addons.zip"
CHECK_INTERVAL = 3600
RETRY_INTERVAL = 900


def _version(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[A-Za-z0-9.-]+)?", value)
    if not match:
        raise ValueError("Invalid release version")
    return (*map(int, match.group(1, 2, 3)), 0 if match.group(4) else 1)


def _fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": f"AzerothAddons/{__version__}", "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=15, context=create_ssl_context()) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release response too large")
    return data


async def fetch_release(url: str, limit: int) -> bytes:
    return await asyncio.to_thread(_fetch, url, limit)


class PluginUpdates:
    def __init__(self, settings: SettingsStore, current_version: str = __version__) -> None:
        self.settings = settings
        self.current_version = current_version
        self._lock = asyncio.Lock()
        self._attempt: float | None = None
        self._status: dict[str, Any] = {"state": "unchecked", "checkedAt": None, "release": None, "message": None}

    def status(self) -> dict[str, Any]:
        return {**self._status, "currentVersion": self.current_version,
                "automatic": bool(self.settings.get("autoCheckPluginUpdates", True)),
                "manualDownloadUrl": DOWNLOAD_URL}

    async def check(self, force: bool = False) -> dict[str, Any]:
        async with self._lock:
            if not force and not self.settings.get("autoCheckPluginUpdates", True):
                return {**self.status(), "state": "disabled"}
            interval = RETRY_INTERVAL if self._status["state"] == "error" else CHECK_INTERVAL
            if not force and self._attempt is not None and time.monotonic() - self._attempt < interval:
                return self.status()
            self._attempt = time.monotonic()
            try:
                raw = json.loads(await fetch_release(LATEST_URL, 1024 * 1024))
                release = await self._parse(raw)
                newer = _version(release["version"]) > _version(self.current_version)
                self._status = {"state": "available" if newer else "up-to-date",
                                "checkedAt": time.time(), "release": release if newer else None, "message": None}
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                # Network/rate-limit failures are local updater state, not repeated
                # telemetry errors or a reason to stop addon management.
                self._status = {"state": "error", "checkedAt": time.time(), "release": None,
                                "message": "Could not check GitHub releases. Try again later or install from URL."}
            return self.status()

    async def _parse(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or raw.get("draft") is not False or raw.get("prerelease") is not False:
            raise ValueError("Only public stable releases are eligible")
        tag = raw["tag_name"]
        if not isinstance(tag, str) or not tag.startswith("v") or "-" in tag:
            raise ValueError("Expected stable version tag")
        version = tag[1:]
        _version(version)
        base = f"{RELEASES_URL}/download/{tag}/"
        assets = raw["assets"]
        asset = next((item for item in assets if item.get("name") == "azeroth-addons.zip"), None)
        if not asset or asset.get("browser_download_url") != base + "azeroth-addons.zip" or asset.get("state") != "uploaded":
            raise ValueError("Missing official ZIP asset")
        digest = asset.get("digest")
        if digest is None:
            checksum = next((item for item in assets if item.get("name") == "azeroth-addons.zip.sha256"), None)
            if not checksum or checksum.get("browser_download_url") != base + "azeroth-addons.zip.sha256" or checksum.get("state") != "uploaded":
                raise ValueError("Missing checksum")
            contents = (await fetch_release(base + "azeroth-addons.zip.sha256", 1024)).decode("ascii").strip()
            match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?azeroth-addons\.zip", contents)
            if not match:
                raise ValueError("Invalid checksum file")
            digest = "sha256:" + match.group(1)
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            raise ValueError("Invalid checksum")
        return {"version": version, "tag": tag, "url": f"{RELEASES_URL}/tag/{tag}",
                "assetUrl": base + "azeroth-addons.zip", "sha256": digest[7:].lower(),
                "notes": str(raw.get("body") or "")[:12000]}

    def install_plan(self, expected_version: str) -> dict[str, Any]:
        release = self._status.get("release")
        if self._status["state"] != "available" or not release:
            raise AzerothAddonsError(NOT_READY, "Check for a plugin update first.")
        if release["version"] != expected_version:
            raise AzerothAddonsError(INVALID_ARGUMENT, "The available release changed. Review it before updating.")
        return dict(release)
