"""Privacy scrubbing.

Everything that enters the error journal passes through here first, so
sensitive text never reaches the journal file - let alone a remote endpoint.

The rules:

1. Credential-shaped values are removed (delegated to :mod:`logctx`).
2. Absolute paths are rewritten so they never carry a username:
   ``/home/deck/x`` becomes ``~/x`` and ``/run/media/deck/SDCARD`` becomes
   ``/run/media/<user>/SDCARD``.
3. Mappings with credential-looking keys keep the key but lose the value.
4. Every field is length-capped so one runaway traceback cannot bloat the log.

Bare words are never replaced: the SteamOS username is ``deck``, and blanking
every occurrence would mangle "Steam Deck" or "decky" in messages.
"""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from ..logctx import redact as redact_credentials

HOME_PLACEHOLDER = "~"
USER_PLACEHOLDER = "<user>"

MAX_FIELD_CHARS = 4000
MAX_CONTAINER_ITEMS = 50

# Keys whose *value* is never recorded. Deliberately broad: over-redacting a
# diagnostic field is harmless, leaking a credential is not.
SENSITIVE_KEY = re.compile(
    r"(?i)("
    r"api[-_]?key|api[-_]?token|access[-_]?token|auth[-_]?token|\btoken\b|\bdsn\b|"
    r"secret|password|passwd|authorization|bearer|credential|private"
    r")"
)

# Absolute POSIX-ish path tokens, and Windows user paths.
_POSIX_PATH = re.compile(r"(?<![\w~])(/(?:[^\s\"'()\[\]{},;:]+))")
_WINDOWS_USER = re.compile(r"(?i)([a-z]:\\users\\)([^\\\s\"']+)")

# Path prefixes whose first component is a user name.
_USER_PREFIXES = ("/home/", "/var/home/", "/Users/", "/run/media/", "/media/")

# The plugin's own directory. When configured, paths inside it are rewritten
# relative (``backend/azeroth_addons/...``) instead of leaking where the plugin
# happens to live.
_PLUGIN_ROOT: str | None = None


def configure(*, plugin_root: str | os.PathLike[str] | None = None) -> None:
    """Tell the scrubber where the plugin lives so its paths become relative."""
    global _PLUGIN_ROOT
    if plugin_root is None:
        _PLUGIN_ROOT = None
        return
    root = str(plugin_root).rstrip("/")
    _PLUGIN_ROOT = root or None


def home_dir() -> str:
    return os.path.expanduser("~")


def scrub_path(token: str) -> str:
    """Rewrite one path token so it cannot identify a user."""
    if _PLUGIN_ROOT:
        if token == _PLUGIN_ROOT:
            return "<plugin>"
        if token.startswith(_PLUGIN_ROOT + "/"):
            return token[len(_PLUGIN_ROOT) + 1 :]

    home = home_dir()
    if token == home:
        return HOME_PLACEHOLDER
    if token.startswith(home + "/"):
        return HOME_PLACEHOLDER + token[len(home) :]

    for prefix in _USER_PREFIXES:
        if not token.startswith(prefix):
            continue
        remainder = token[len(prefix) :]
        head, _, tail = remainder.partition("/")
        if head:
            rebuilt = USER_PLACEHOLDER + ("/" + tail if tail else "")
            return prefix + rebuilt
    return token


def scrub(text: str | None) -> str | None:
    """Redact credentials, usernames and oversized text from a string."""
    if not text:
        return text
    cleaned = redact_credentials(str(text))
    cleaned = _POSIX_PATH.sub(lambda match: scrub_path(match.group(1)), cleaned)
    cleaned = _WINDOWS_USER.sub(lambda match: f"{match.group(1)}{USER_PLACEHOLDER}", cleaned)
    # Control characters make the journal hard to read and can confuse terminals.
    cleaned = "".join(ch if ch == "\n" or ch == "\t" or ch >= " " else " " for ch in cleaned)
    if len(cleaned) > MAX_FIELD_CHARS:
        cleaned = cleaned[:MAX_FIELD_CHARS] + f"\n…[truncated {len(cleaned) - MAX_FIELD_CHARS} chars]"
    return cleaned


def scrub_value(value: Any) -> Any:
    """Recursively scrub an arbitrary JSON-ish value."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, Mapping):
        return scrub_mapping(value)
    if isinstance(value, (list, tuple)):
        return [scrub_value(item) for item in list(value)[:MAX_CONTAINER_ITEMS]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return scrub(str(value))


def scrub_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Scrub a mapping, dropping values behind credential-looking keys."""
    out: dict[str, Any] = {}
    for index, (key, value) in enumerate(mapping.items()):
        if index >= MAX_CONTAINER_ITEMS:
            break
        name = str(key)
        if value in (None, ""):
            continue
        if SENSITIVE_KEY.search(name):
            out[name] = "<redacted>"
            continue
        out[name] = scrub_value(value)
    return out


def contains_home_path(text: str) -> bool:
    """Test helper: would this text expose the user's home directory?"""
    return home_dir() in text
