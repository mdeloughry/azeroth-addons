# Type stub for the `decky` module injected by Decky Loader at runtime.
# See https://wiki.deckbrew.xyz/en/plugin-dev/env-vars for the constants.

import logging
from typing import Any, Callable

HOME: str
USER: str
DECKY_VERSION: str
DECKY_USER: str
DECKY_USER_HOME: str
DECKY_HOME: str
DECKY_PLUGIN_SETTINGS_DIR: str
DECKY_PLUGIN_RUNTIME_DIR: str
DECKY_PLUGIN_LOG_DIR: str
DECKY_PLUGIN_DIR: str
DECKY_PLUGIN_NAME: str
DECKY_PLUGIN_VERSION: str
DECKY_PLUGIN_AUTHOR: str
DECKY_PLUGIN_LOG: str

logger: logging.Logger

async def emit(event: str, *args: Any) -> None: ...

def migrate_any(target_dir: str, *files_or_dirs: str) -> dict[str, list[str]]: ...
def migrate_settings(target_dir: str, *files: str) -> dict[str, list[str]]: ...
def migrate_runtime(target_dir: str, *files: str) -> dict[str, list[str]]: ...
def migrate_logs(target_dir: str, *files: str) -> dict[str, list[str]]: ...
