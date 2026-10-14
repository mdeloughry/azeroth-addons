"""Persistence.

All state lives in JSON files under Decky's per-plugin settings directory.
Two stores are used:

* ``installations.json`` / ``settings.json`` - non-secret state;
* ``credentials.json`` - provider credentials, written with mode 0600.

Nothing here depends on Decky, so the module is directly testable.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import CONFIG_ERROR, AzerothAddonsError
from .logctx import get_logger

INSTALLATIONS_FILE = "installations.json"
SETTINGS_FILE = "settings.json"
CREDENTIALS_FILE = "credentials.json"


class JsonStore:
    """Small atomic JSON store. Writes go through a temp file + rename."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)

    def path(self, name: str) -> Path:
        return self.directory / name

    def read(self, name: str, default: Any) -> Any:
        path = self.path(name)
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            get_logger().warning("could not read %s: %s", path, exc)
            return default

    def write(self, name: str, data: Any, *, private: bool = False) -> None:
        path = self.path(name)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(self.directory), prefix=f".{name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                # Restrict permissions before the file becomes visible under its real name.
                if private:
                    os.chmod(tmp_name, 0o600)
                os.replace(tmp_name, path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise AzerothAddonsError(
                CONFIG_ERROR,
                "Could not save Azeroth Addons settings.",
                details=f"file={path} error={exc}",
            ) from exc


class InstallationStore:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def load(self) -> list[dict[str, Any]]:
        raw = self._store.read(INSTALLATIONS_FILE, {"installations": []})
        if isinstance(raw, list):  # tolerate a bare list from older builds
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            items = raw.get("installations", [])
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def save(self, records: list[dict[str, Any]]) -> None:
        self._store.write(INSTALLATIONS_FILE, {"version": 1, "installations": records})


DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "selectedInstallationId": None,
    "enableExperimentalRollback": False,
    "enableDirectCurseForge": False,
    "curseForgeServiceUrl": None,
    "sourcePreference": "automatic",
    "autoCheckUpdates": True,
    "autoCheckPluginUpdates": True,
    # Error reporting is off unless the user turns it on. A built-in destination
    # is used by default; a user-supplied DSN lives in the credential store,
    # never in plain settings.
    "enableErrorReporting": False,
    "errorReportingFormat": "sentry",
    "errorReportingEndpoint": "",
    # Set once the user answers the opt-in prompt (by enabling reporting or by
    # dismissing it), so the nudge is offered at most once.
    "errorReportingNudgeDismissed": False,
}

# Keys the frontend is allowed to write. Keeps an arbitrary RPC payload from
# introducing new settings.
SETTABLE_KEYS = frozenset(
    {
        "enableExperimentalRollback",
        "enableDirectCurseForge",
        "curseForgeServiceUrl",
        "sourcePreference",
        "autoCheckUpdates",
        "autoCheckPluginUpdates",
        "enableErrorReporting",
        "errorReportingFormat",
        "errorReportingEndpoint",
        "errorReportingNudgeDismissed",
    }
)

# Credentials are stored separately, with mode 0600, and are never returned to
# the frontend - only a masked hint is. The Sentry DSN lives here too: it
# carries a key, and the UI only ever needs a keyless form of it.
CREDENTIAL_KEYS = ("curseforge", "github", "wago", "wowinterface", "sentry")


class SettingsStore:
    def __init__(self, store: JsonStore) -> None:
        self._store = store
        self._settings: dict[str, Any] = {}
        self._credentials: dict[str, str] = {}
        self._loaded = False

    def load(self) -> dict[str, Any]:
        raw = self._store.read(SETTINGS_FILE, {})
        settings = dict(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            settings.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
        self._settings = settings
        raw_creds = self._store.read(CREDENTIALS_FILE, {})
        self._credentials = {}
        if isinstance(raw_creds, dict):
            for key in CREDENTIAL_KEYS:
                value = raw_creds.get(key)
                if isinstance(value, str) and value:
                    self._credentials[key] = value
        self._loaded = True
        return self._settings

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    @property
    def settings(self) -> dict[str, Any]:
        self._ensure()
        return self._settings

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure()
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._ensure()
        self._settings[key] = value
        self._store.write(SETTINGS_FILE, self._settings)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        self._ensure()
        for key, value in values.items():
            if key in SETTABLE_KEYS:
                self._settings[key] = value
        self._store.write(SETTINGS_FILE, self._settings)
        return self._settings

    # --- credentials -------------------------------------------------------

    def credential(self, key: str) -> str | None:
        self._ensure()
        return self._credentials.get(key)

    def credentials(self) -> dict[str, str]:
        self._ensure()
        return dict(self._credentials)

    def set_credential(self, key: str, value: str | None) -> None:
        self._ensure()
        if key not in CREDENTIAL_KEYS:
            raise AzerothAddonsError(CONFIG_ERROR, f"Unknown credential '{key}'.")
        if value:
            self._credentials[key] = value
        else:
            self._credentials.pop(key, None)
        self._store.write(CREDENTIALS_FILE, self._credentials, private=True)

    def has_credential(self, key: str) -> bool:
        self._ensure()
        return key in self._credentials
