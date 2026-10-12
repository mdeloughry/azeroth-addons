"""Read-only search of the same public catalogue used by instawow 7.2.1.

The upstream CLI search opens an interactive install picker, so it cannot be
used as a machine-readable search API by Decky.
"""

from __future__ import annotations

import asyncio
import re
import time
from difflib import SequenceMatcher
from typing import Any

from ..errors import SEARCH_FAILED, AzerothAddonsError
from ..providers.http import fetch_json

CATALOGUE_VERSION = 8
CATALOGUE_URL = (
    "https://raw.githubusercontent.com/layday/instawow-data/data/"
    "base-catalogue-v8.compact.json"
)
CACHE_SECONDS = 4 * 60 * 60


def _normalise(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


class CatalogueSearch:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] | None = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def _load(self) -> list[dict[str, Any]]:
        async with self._lock:
            if self._entries is not None and time.monotonic() - self._loaded_at < CACHE_SECONDS:
                return self._entries
            payload = await fetch_json(CATALOGUE_URL, provider="instawow", timeout=30.0)
            if (
                not isinstance(payload, dict)
                or payload.get("version") != CATALOGUE_VERSION
                or not isinstance(payload.get("entries"), list)
            ):
                raise AzerothAddonsError(
                    SEARCH_FAILED,
                    "The addon catalogue returned an unsupported format.",
                    engine="instawow",
                )
            self._entries = [
                entry for entry in payload["entries"]
                if isinstance(entry, dict)
                and all(isinstance(entry.get(key), str) and entry[key] for key in ("source", "id", "name"))
                and isinstance(entry.get("game_flavours"), list)
            ]
            self._loaded_at = time.monotonic()
            return self._entries

    async def search(self, query: str, *, flavour: str | None, limit: int = 25, sources: set[str] | None = None) -> list[dict[str, Any]]:
        needle = _normalise(query)
        if not needle or limit <= 0:
            return []
        entries = await self._load()
        matches: list[tuple[float, str, dict[str, Any]]] = []
        for entry in entries:
            if sources is not None and entry["source"] not in sources:
                continue
            if flavour not in entry["game_flavours"]:
                continue
            name = _normalise(entry["name"])
            if needle == name:
                score = 3.0
            elif needle in name:
                # Long subtitles must not bury core addons under dozens of
                # shorter audio/language packs (e.g. Spoken Everything).
                title = _normalise(entry["name"].split(":", 1)[0])
                match_name = title if needle in title else name
                score = 2.0 + len(needle) / max(1, len(match_name))
            elif all(token in name for token in needle.split()):
                score = 1.0
            else:
                score = SequenceMatcher(None, needle, name).ratio()
                if score < 0.7:
                    continue
            if "retired" in name.split() or "deprecated" in name.split():
                score -= 0.5
            matches.append((score, name, entry))
        matches.sort(key=lambda item: (-item[0], item[1]))
        return [entry for _, _, entry in matches[:limit]]
