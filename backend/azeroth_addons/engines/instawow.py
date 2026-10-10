"""The instawow engine.

``InstawowAdapter`` is the **only** place in Azeroth Addons that knows
instawow's command-line syntax. Everything above it (service, RPC, frontend)
speaks the provider-neutral domain model.

Why a subprocess rather than an import: instawow requires Python >= 3.13 and
Decky's plugin backend runs on Python 3.11, so the bundled standalone binary is
invoked as a child process. That also keeps a crashing engine away from the
plugin process.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from .. import BUNDLED_INSTAWOW_VERSION
from ..addons.models import (
    STATE_UPDATE_AVAILABLE,
    Addon,
    addon_from_engine,
    unmanaged_addon,
)
from ..errors import (
    ADDON_NOT_FOUND,
    ENGINE_FAILED,
    ENGINE_UNAVAILABLE,
    ENGINE_UNSUPPORTED,
    INSTALL_FAILED,
    INSTAWOW_INCOMPATIBLE,
    INSTAWOW_MISSING,
    PROVIDER_UNAVAILABLE,
    REMOVE_FAILED,
    ROLLBACK_FAILED,
    SEARCH_FAILED,
    UPDATE_FAILED,
    AzerothAddonsError,
    error_from_process_failure,
)
from ..installations.models import WowInstallation
from ..logctx import ctx, get_logger, redact, safe_env
from ..security import canonical, validate_addons_target
from ..settings import SettingsStore
from .base import (
    STATE_ERROR,
    STATE_INCOMPATIBLE,
    STATE_MISSING,
    STATE_READY,
    STATE_UNKNOWN,
    STATE_VERIFYING,
    STATE_WARMING,
    AddonEngine,
    EngineCapabilities,
    EngineStatus,
    ReconcileResult,
)

logger = get_logger()

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_DEFN = re.compile(r"\b(curse|github|tukui|wowi|wago|instawow):([A-Za-z0-9_.\-/]+)")
_VERSION_ARROW = re.compile(r"(\S+)\s*(?:->|=>|→|-->)\s*(\S+)")
_VERSION = re.compile(r"(\d+(?:\.\d+){1,3})")

# instawow source id  <->  our provider id
SOURCE_TO_PROVIDER: dict[str, str] = {
    "curse": "curseforge",
    "github": "github",
    "tukui": "tukui",
    "wowi": "wowinterface",
    "wago": "wago",
    "instawow": "instawow",
}
PROVIDER_TO_SOURCE: dict[str, str] = {value: key for key, value in SOURCE_TO_PROVIDER.items()}

# Provider id -> environment variable suffix used by instawow for access tokens.
TOKEN_ENV_SUFFIX: dict[str, str] = {
    "curseforge": "CFCORE",
    "github": "GITHUB",
    "wago": "WAGO",
    "wowinterface": "WOWI",
}

# Actions that must not run while the game is open.
MUTATING_OPERATIONS = frozenset({"install", "update", "remove", "rollback", "update_all"})


def provider_to_source(provider: str) -> str:
    source = PROVIDER_TO_SOURCE.get(provider)
    if not source:
        raise AzerothAddonsError(
            PROVIDER_UNAVAILABLE,
            f"'{provider}' is not a supported addon source.",
            provider=provider,
            details=f"known={sorted(PROVIDER_TO_SOURCE)}",
        )
    return source


def source_to_provider(source: str) -> str:
    return SOURCE_TO_PROVIDER.get(source, source)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def definition_for(provider: str, provider_id: str) -> str:
    return f"{provider_to_source(provider)}:{provider_id}"


# ---------------------------------------------------------------------------
# output parsing (pure functions - unit tested against canned output)
# ---------------------------------------------------------------------------


@dataclass
class ManagedPackage:
    source: str
    ident: str
    version: str | None = None
    name: str | None = None
    folder_name: str | None = None
    pinned: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def provider(self) -> str:
        return source_to_provider(self.source)

    def to_addon(self) -> Addon:
        return addon_from_engine(
            provider=self.provider,
            provider_id=self.ident,
            version=self.version,
            name=self.name or self.ident,
            folder_name=self.folder_name,
            pinned=self.pinned,
        )


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for key in ("version", "value", "string", "display"):
            if key in value:
                return _as_text(value[key])
        return None
    if isinstance(value, (list, tuple)):
        return _as_text(value[0]) if value else None
    return str(value)


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _definition_parts(record: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Extract (source, id) from whatever shape the engine serialised."""
    defn = record.get("defn")
    if isinstance(defn, str) and ":" in defn:
        source, _, ident = defn.partition(":")
        return source, ident
    if isinstance(defn, dict):
        source = defn.get("source") or defn.get("source_id")
        ident = defn.get("id") or defn.get("slug")
        if source or ident:
            return (_as_text(source), _as_text(ident))
    source = _as_text(_first_present(record, "source", "source_id", "sourceId", "sourceName"))
    ident = _as_text(_first_present(record, "id", "slug", "addon_id", "addonId", "alias"))
    return source, ident


def parse_packages(payload: Any) -> tuple[list[ManagedPackage], int]:
    """Parse ``instawow list --format json`` output tolerantly.

    Returns ``(packages, unparsed_count)``. A non-zero unparsed count means the
    engine's serialisation changed and is logged as a warning rather than
    silently producing an empty list.
    """
    records: list[Any]
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("packages", "installed", "addons", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        else:
            records = [payload] if "id" in payload or "slug" in payload else []
    else:
        records = []

    packages: list[ManagedPackage] = []
    unparsed = 0
    for record in records:
        if not isinstance(record, dict):
            unparsed += 1
            continue
        source, ident = _definition_parts(record)
        if not source or not ident:
            unparsed += 1
            continue
        packages.append(
            ManagedPackage(
                source=source,
                ident=ident,
                version=_as_text(_first_present(record, "version", "installed_version", "installedVersion")),
                name=_as_text(_first_present(record, "name", "title", "display_name")),
                folder_name=_as_text(_first_present(record, "folder_name", "folderName", "folder")),
                pinned=bool(_first_present(record, "pinned", "isPinned") or False),
                raw=record,
            )
        )
    return packages, unparsed


@dataclass
class UpdateTarget:
    source: str
    ident: str
    from_version: str | None = None
    to_version: str | None = None

    @property
    def provider(self) -> str:
        return source_to_provider(self.source)


def parse_update_targets(text: str) -> list[UpdateTarget]:
    """Parse ``instawow update --dry-run`` output into update targets."""
    targets: dict[tuple[str, str], UpdateTarget] = {}
    for raw_line in strip_ansi(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for match in _DEFN.finditer(line):
            key = (match.group(1), match.group(2))
            target = targets.setdefault(key, UpdateTarget(source=match.group(1), ident=match.group(2)))
            arrow = _VERSION_ARROW.search(line)
            if arrow:
                target.from_version = _clean_version(arrow.group(1))
                target.to_version = _clean_version(arrow.group(2))
    return list(targets.values())


def _clean_version(token: str) -> str | None:
    match = _VERSION.search(token)
    return match.group(1) if match else None


def parse_search_results(text: str) -> list[tuple[str, str, str | None]]:
    """Parse ``instawow search`` output into ``(source, id, name)`` triples.

    Only lines carrying an explicit ``source:id`` definition are kept: an
    unattributable result cannot be installed safely, so it is dropped rather
    than guessed at.
    """
    results: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in strip_ansi(text).splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = _DEFN.search(line)
        if not match:
            continue
        key = (match.group(1), match.group(2))
        if key in seen:
            continue
        seen.add(key)
        remainder = (line[: match.start()] + " " + line[match.end() :]).strip(" \t|-–—:")
        name = remainder.strip() or None
        results.append((key[0], key[1], name))
    return results


# ---------------------------------------------------------------------------
# the adapter - the only CLI-aware class
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def combined(self) -> str:
        return f"{self.stdout}\n{self.stderr}"

    def tail(self, limit: int = 3000) -> str:
        text = strip_ansi(self.combined).strip()
        return text[-limit:] if len(text) > limit else text


class InstawowAdapter:
    """Wraps the bundled instawow binary. Knows CLI syntax; nothing else does."""

    def __init__(
        self,
        binary_path: str | os.PathLike[str],
        home_dir: str | os.PathLike[str],
        *,
        token_provider: Callable[[], Mapping[str, str]] | None = None,
        base_timeout: float = 180.0,
    ) -> None:
        self.binary = Path(binary_path)
        self.home = Path(home_dir)
        self._token_provider = token_provider or (lambda: {})
        self.base_timeout = base_timeout

    # --- bootstrap ---------------------------------------------------------

    def exists(self) -> bool:
        return self.binary.is_file()

    def ensure_executable(self) -> bool:
        if not self.exists():
            return False
        try:
            mode = self.binary.stat().st_mode
            if not mode & stat.S_IXUSR:
                os.chmod(self.binary, mode | 0o755)
        except OSError as exc:
            logger.warning("could not mark %s executable: %s", self.binary, exc)
            return False
        return os.access(self.binary, os.X_OK)

    def environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env["INSTAWOW_HOME"] = str(self.home)
        env["NO_COLOR"] = "1"
        env.setdefault("TERM", "dumb")
        tokens = self._token_provider() or {}
        for provider, suffix in TOKEN_ENV_SUFFIX.items():
            value = tokens.get(provider)
            if value:
                env[f"INSTAWOW_ACCESS_TOKENS_{suffix}"] = value
        return env

    def loggable_environment(self) -> dict[str, str]:
        return safe_env(self.environment())

    # --- invocation --------------------------------------------------------

    async def run(
        self,
        args: Sequence[str],
        *,
        profile: str | None = None,
        timeout: float | None = None,
        stdin: str | None = None,
    ) -> RunResult:
        argv = [str(self.binary)]
        if profile:
            argv.extend(["--profile", profile])
        argv.extend(str(arg) for arg in args)

        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                env=self.environment(),
            )
        except OSError as exc:
            raise AzerothAddonsError(
                INSTAWOW_MISSING,
                "The bundled addon engine could not be started.",
                engine="instawow",
                details=f"binary={self.binary} error={exc}",
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin.encode("utf-8") if stdin is not None else None),
                timeout=timeout or self.base_timeout,
            )
        except asyncio.TimeoutError:
            with_suppress = getattr(process, "kill", None)
            if with_suppress:
                process.kill()
            await process.wait()
            duration = int((time.monotonic() - started) * 1000)
            logger.warning("instawow timed out after %sms: %s", duration, argv[1:])
            return RunResult(argv, -1, "", "Operation timed out.", duration, timed_out=True)

        duration = int((time.monotonic() - started) * 1000)
        result = RunResult(
            argv=argv,
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout_bytes.decode("utf-8", "replace"),
            stderr=stderr_bytes.decode("utf-8", "replace"),
            duration_ms=duration,
        )
        logger.debug(
            "instawow %s exit=%s duration=%sms",
            ctx(engine="instawow", operation=argv[-2] if len(argv) > 1 else "run"),
            result.returncode,
            duration,
        )
        return result

    # --- configuration -----------------------------------------------------

    @property
    def config_dir(self) -> Path:
        return self.home / "config"

    def global_config_path(self) -> Path:
        return self.config_dir / "config.json"

    def profile_config_path(self, profile: str) -> Path:
        return self.config_dir / "profiles" / profile / "config.json"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.", delete=False
        )
        try:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, path)

    def write_global_config(self) -> None:
        path = self.global_config_path()
        if path.exists():
            return
        self._write_json(path, {"auto_update_check": True})

    def write_profile_config(
        self,
        profile: str,
        addon_dir: str | os.PathLike[str],
        flavour_override: str | None = None,
    ) -> Path:
        path = self.profile_config_path(profile)
        self._write_json(
            path,
            {
                "profile": profile,
                "addon_dir": str(canonical(addon_dir)),
                "flavour_override": flavour_override,
            },
        )
        return path

    def read_profile_config(self, profile: str) -> dict[str, Any]:
        path = self.profile_config_path(profile)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    # --- commands ----------------------------------------------------------

    async def version(self, timeout: float = 300.0) -> str | None:
        """Run ``--version``. This also performs the engine's first-run bootstrap."""
        result = await self.run(["--version"], timeout=timeout)
        if not result.ok:
            self._raise_startup_failure(result)
        match = _VERSION.search(strip_ansi(result.combined))
        return match.group(1) if match else None

    def _raise_startup_failure(self, result: RunResult) -> None:
        text = strip_ansi(result.combined)
        if result.timed_out:
            raise AzerothAddonsError(
                ENGINE_FAILED,
                "The addon engine took too long to start. Its first launch downloads its Python runtime.",
                engine="instawow",
                details=result.tail(),
            )
        lowered = text.lower()
        if (
            result.returncode in (126, 127)
            or "glibc" in lowered
            or "cannot execute" in lowered
            or "exec format error" in lowered
            or "no such file" in lowered
        ):
            raise AzerothAddonsError(
                INSTAWOW_INCOMPATIBLE,
                "The bundled addon engine cannot run on this system.",
                engine="instawow",
                details=result.tail(),
            )
        raise AzerothAddonsError(
            ENGINE_FAILED,
            "The bundled addon engine failed to start.",
            engine="instawow",
            details=result.tail(),
        )

    async def list_packages(self, profile: str) -> tuple[list[ManagedPackage], int]:
        result = await self.run(["list", "--format", "json"], profile=profile, timeout=180.0)
        if not result.ok:
            raise self.failure(result, ENGINE_FAILED, "Could not read the installed addon list.")
        text = strip_ansi(result.stdout).strip()
        if not text:
            return [], 0
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Older builds may print a banner line before the JSON document.
            start = text.find("[")
            brace = text.find("{")
            candidates = [index for index in (start, brace) if index >= 0]
            if not candidates:
                raise AzerothAddonsError(
                    ENGINE_FAILED,
                    "The addon engine returned an unreadable addon list.",
                    engine="instawow",
                    details=result.tail(),
                )
            try:
                payload = json.loads(text[min(candidates) :])
            except json.JSONDecodeError as exc:
                raise AzerothAddonsError(
                    ENGINE_FAILED,
                    "The addon engine returned an unreadable addon list.",
                    engine="instawow",
                    details=result.tail(),
                ) from exc
        return parse_packages(payload)

    async def debug(self, profile: str) -> dict[str, Any]:
        result = await self.run(["debug"], profile=profile, timeout=60.0)
        if not result.ok:
            raise self.failure(result, ENGINE_FAILED, "Could not read the engine configuration.")
        try:
            payload = json.loads(strip_ansi(result.stdout).strip() or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async def reconcile_auto(self, profile: str) -> RunResult:
        return await self.run(["reconcile", "--auto"], profile=profile, timeout=300.0)

    async def update_dry_run(self, profile: str) -> RunResult:
        return await self.run(["update", "--dry-run"], profile=profile, timeout=600.0)

    async def install(self, profile: str, definition: str, *, replace: bool = False) -> RunResult:
        args = ["install", definition]
        if replace:
            args.append("--replace")
        return await self.run(args, profile=profile, timeout=900.0)

    async def update(self, profile: str, definition: str | None = None) -> RunResult:
        args = ["update"]
        if definition:
            args.append(definition)
        return await self.run(args, profile=profile, timeout=900.0)

    async def remove(self, profile: str, definition: str) -> RunResult:
        return await self.run(["remove", definition], profile=profile, timeout=300.0)

    async def rollback(self, profile: str, definition: str, *, choice: str = "1") -> RunResult:
        # instawow's rollback is an interactive version picker; feed it the
        # requested choice. If it refuses to run without a TTY the caller
        # receives a clear, structured failure.
        return await self.run(
            ["rollback", definition],
            profile=profile,
            timeout=300.0,
            stdin=f"{choice}\n",
        )

    async def search(self, profile: str, query: str, *, limit: int = 25) -> RunResult:
        return await self.run(
            ["search", query, "--limit", str(max(1, limit))],
            profile=profile,
            timeout=180.0,
        )

    def failure(self, result: RunResult, code: str, message: str, **context: Any) -> AzerothAddonsError:
        """Build a structured error from a failed engine invocation.

        Credentials are stripped from the captured output before it becomes an
        error detail, so a chatty engine can never leak a token into the UI.
        """
        return error_from_process_failure(
            code,
            message,
            returncode=result.returncode,
            stderr=self.redact(result.tail()),
            engine="instawow",
            **context,
        )

    def redact(self, text: str) -> str:
        """Remove any configured credential value from arbitrary text."""
        tokens = self._token_provider() or {}
        redacted = text
        for value in tokens.values():
            if value and len(value) >= 4:
                redacted = redacted.replace(value, "<redacted>")
        return redact(redacted)


# ---------------------------------------------------------------------------
# the engine
# ---------------------------------------------------------------------------

StatusCallback = Callable[[EngineStatus], Awaitable[None]]


class InstawowEngine(AddonEngine):
    engine_id = "instawow"
    display_name = "instawow"

    def __init__(
        self,
        adapter: InstawowAdapter,
        *,
        settings: SettingsStore | None = None,
        bundled_version: str = BUNDLED_INSTAWOW_VERSION,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self._adapter = adapter
        self._settings = settings
        self._bundled_version = bundled_version
        self._status_callback = status_callback
        self._state = STATE_UNKNOWN
        self._version: str | None = None
        self._message: str | None = None
        self._detail: str | None = None
        self._prepare_lock = asyncio.Lock()

    # --- lifecycle ---------------------------------------------------------

    def capabilities(self) -> EngineCapabilities:
        rollback = bool(self._settings.get("enableExperimentalRollback", False)) if self._settings else False
        return EngineCapabilities(
            install=True,
            update=True,
            remove=True,
            reconcile=True,
            rollback=rollback,
            search=True,
            list_installed=True,
        )

    def _snapshot(self) -> EngineStatus:
        return EngineStatus(
            engine_id=self.engine_id,
            display_name=self.display_name,
            state=self._state,
            available=self._state == STATE_READY,
            version=self._version,
            bundled_version=self._bundled_version,
            message=self._message,
            detail=self._detail,
            capabilities=self.capabilities(),
        )

    async def status(self) -> EngineStatus:
        return self._snapshot()

    async def _publish(self, state: str, message: str | None = None, detail: str | None = None) -> None:
        self._state = state
        self._message = message
        self._detail = detail
        if self._status_callback is not None:
            try:
                await self._status_callback(self._snapshot())
            except Exception as exc:  # noqa: BLE001 - never let a UI callback break the engine
                logger.debug("status callback failed: %s", exc)

    async def prepare(self) -> EngineStatus:
        async with self._prepare_lock:
            if not self._adapter.exists():
                await self._publish(
                    STATE_MISSING,
                    "The bundled addon engine is missing.",
                    f"Expected {self._adapter.binary}",
                )
                return self._snapshot()

            if not self._adapter.ensure_executable():
                await self._publish(
                    STATE_ERROR,
                    "The bundled addon engine is not executable.",
                    f"Path {self._adapter.binary}",
                )
                return self._snapshot()

            await self._publish(STATE_VERIFYING, "Checking the addon engine…")
            self._adapter.write_global_config()
            try:
                await self._publish(
                    STATE_WARMING,
                    "Starting the addon engine…",
                    "The first launch downloads the engine's Python runtime.",
                )
                version = await self._adapter.version()
            except AzerothAddonsError as exc:
                state = STATE_INCOMPATIBLE if exc.code == INSTAWOW_INCOMPATIBLE else STATE_ERROR
                await self._publish(state, exc.message, exc.details)
                return self._snapshot()

            self._version = version
            await self._publish(
                STATE_READY,
                f"instawow {version} ready" if version else "Addon engine ready",
            )
            logger.info(
                "engine ready version=%s %s",
                version,
                ctx(engine=self.engine_id, operation="prepare"),
            )
            return self._snapshot()

    async def _require_ready(self) -> None:
        if self._state == STATE_READY:
            return
        status = await self.prepare()
        if not status.available:
            raise AzerothAddonsError(
                ENGINE_UNAVAILABLE,
                status.message or "The addon engine is not available.",
                details=status.detail,
                engine=self.engine_id,
            )

    # --- profile plumbing --------------------------------------------------

    def _profile(self, installation: WowInstallation) -> str:
        return installation.engine_profile or f"az-{installation.id}"

    async def ensure_profile(self, installation: WowInstallation) -> Path:
        """Write (or refresh) the engine profile for one installation."""
        addons_path = validate_addons_target(installation.addons_path, installation.root_path)
        profile = self._profile(installation)
        flavour = installation.instawow_flavour
        if installation.flavour == "unknown":
            flavour = None
        self._adapter.write_global_config()
        self._adapter.write_profile_config(profile, addons_path, flavour)
        return addons_path

    async def profile_status(self, installation: WowInstallation) -> dict[str, Any]:
        await self._require_ready()
        try:
            profile = self._profile(installation)
            await self.ensure_profile(installation)
            debug = await self._adapter.debug(profile)
            config = self._adapter.read_profile_config(profile)
            active = debug.get("profile") if isinstance(debug.get("profile"), dict) else None
            addon_dir = None
            if isinstance(active, dict):
                addon_dir = active.get("addon_dir")
            return {
                "profile": profile,
                "configPath": str(self._adapter.profile_config_path(profile)),
                "addonDir": addon_dir or config.get("addon_dir"),
                "flavourOverride": (active or {}).get("flavour_override") or config.get("flavour_override"),
                "validated": bool(active),
            }
        except AzerothAddonsError as exc:
            return {"profile": self._profile(installation), "validated": False, "error": exc.to_dict()}

    # --- addon state -------------------------------------------------------

    async def list_installed(self, installation: WowInstallation) -> list[Addon]:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        try:
            packages, unparsed = await self._adapter.list_packages(profile)
        except AzerothAddonsError as exc:
            raise exc.with_context(installation_id=installation.id, engine=self.engine_id)
        if unparsed:
            logger.warning(
                "instawow list: %d record(s) could not be parsed (engine output schema may have changed) %s",
                unparsed,
                ctx(installation=installation.id, engine=self.engine_id, operation="list"),
            )
        addons = [package.to_addon() for package in packages]
        if not addons:
            logger.debug(
                "no managed addons %s",
                ctx(installation=installation.id, engine=self.engine_id, operation="list"),
            )
        return addons

    def _managed_folders(self, managed: Sequence[Addon]) -> set[str]:
        folders: set[str] = set()
        for addon in managed:
            if addon.folder_name:
                folders.add(addon.folder_name.lower())
            if addon.provider_id:
                folders.add(addon.provider_id.lower())
            if addon.name:
                folders.add(addon.name.lower())
        return folders

    def _find_unmanaged(self, installation: WowInstallation, managed: Sequence[Addon]) -> list[Addon]:
        addons_path = canonical(installation.addons_path)
        if not addons_path.is_dir():
            return []
        covered = self._managed_folders(managed)
        unmanaged: list[Addon] = []
        try:
            entries = sorted(os.scandir(addons_path), key=lambda entry: entry.name.lower())
        except OSError as exc:
            logger.warning("could not read %s: %s", addons_path, exc)
            return []
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            name = entry.name
            lowered = name.lower()
            if lowered in covered:
                continue
            # A managed package often owns sibling folders (ElvUI -> ElvUI_Config).
            if any(lowered.startswith(f"{folder}_") or lowered.startswith(f"{folder}-") for folder in covered):
                continue
            unmanaged.append(unmanaged_addon(name))
        return unmanaged

    async def reconcile(self, installation: WowInstallation) -> ReconcileResult:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        try:
            result = await self._adapter.reconcile_auto(profile)
            if not result.ok:
                logger.warning(
                    "instawow reconcile did not complete cleanly %s: %s",
                    ctx(installation=installation.id, engine=self.engine_id, operation="reconcile"),
                    result.tail(500),
                )
        except AzerothAddonsError as exc:
            logger.warning("instawow reconcile failed: %s", exc.message)

        managed = await self.list_installed(installation)
        unmanaged = self._find_unmanaged(installation, managed)
        logger.info(
            "reconciled managed=%d unmanaged=%d %s",
            len(managed),
            len(unmanaged),
            ctx(installation=installation.id, engine=self.engine_id, operation="reconcile"),
        )
        return ReconcileResult(managed=managed, unmanaged=unmanaged)

    async def check_updates(self, installation: WowInstallation) -> list[Addon]:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        result = await self._adapter.update_dry_run(profile)
        if not result.ok:
            raise self._adapter.failure(
                result,
                UPDATE_FAILED,
                "Could not check for addon updates.",
                installation_id=installation.id,
            )
        targets = parse_update_targets(result.combined)
        if not targets:
            return []

        try:
            installed = await self.list_installed(installation)
        except AzerothAddonsError:
            installed = []
        known = {(addon.provider, addon.provider_id.lower()): addon for addon in installed}

        updates: list[Addon] = []
        for target in targets:
            provider = target.provider
            match = known.get((provider, target.ident.lower()))
            if match is not None:
                match.state = STATE_UPDATE_AVAILABLE
                match.available_version = target.to_version or match.available_version
                updates.append(match)
            else:
                addon = addon_from_engine(
                    provider=provider,
                    provider_id=target.ident,
                    version=target.from_version,
                    name=target.ident,
                )
                addon.state = STATE_UPDATE_AVAILABLE
                addon.available_version = target.to_version
                updates.append(addon)
        logger.info(
            "update check found=%d %s",
            len(updates),
            ctx(installation=installation.id, engine=self.engine_id, operation="check_updates"),
        )
        return updates

    # --- mutations ---------------------------------------------------------

    async def install(
        self,
        installation: WowInstallation,
        provider: str,
        provider_id: str,
        *,
        replace: bool = False,
    ) -> Addon:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        definition = definition_for(provider, provider_id)
        result = await self._adapter.install(profile, definition, replace=replace)
        if not result.ok:
            raise self._adapter.failure(
                result,
                INSTALL_FAILED,
                f"Could not install {provider_id}.",
                installation_id=installation.id,
                provider=provider,
            )
        addon = await self._find_addon(installation, provider, provider_id)
        if addon is None:
            addon = addon_from_engine(provider=provider, provider_id=provider_id, version=None, name=provider_id)
        logger.info(
            "installed %s %s",
            definition,
            ctx(installation=installation.id, engine=self.engine_id, provider=provider, operation="install"),
        )
        return addon

    async def _find_addon(
        self,
        installation: WowInstallation,
        provider: str,
        provider_id: str,
    ) -> Addon | None:
        try:
            installed = await self.list_installed(installation)
        except AzerothAddonsError:
            return None
        wanted = provider_id.lower()
        for addon in installed:
            if addon.provider == provider and addon.provider_id.lower() == wanted:
                return addon
        return None

    async def update(self, installation: WowInstallation, addon: Addon) -> Addon:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        if addon.provider == "unmanaged":
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "This addon is not managed by Azeroth Addons, so it cannot be updated.",
                installation_id=installation.id,
                provider=addon.provider,
            )
        definition = definition_for(addon.provider, addon.provider_id)
        result = await self._adapter.update(profile, definition)
        if not result.ok:
            raise self._adapter.failure(
                result,
                UPDATE_FAILED,
                f"Could not update {addon.display_name}.",
                installation_id=installation.id,
                provider=addon.provider,
            )
        updated = await self._find_addon(installation, addon.provider, addon.provider_id)
        logger.info(
            "updated %s %s",
            definition,
            ctx(
                installation=installation.id,
                engine=self.engine_id,
                provider=addon.provider,
                operation="update",
            ),
        )
        return updated or addon

    async def update_all(self, installation: WowInstallation) -> list[Addon]:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        before = {addon.id: addon.installed_version for addon in await self.list_installed(installation)}
        result = await self._adapter.update(profile, None)
        if not result.ok:
            raise self._adapter.failure(
                result,
                UPDATE_FAILED,
                "Could not update addons.",
                installation_id=installation.id,
            )
        after = await self.list_installed(installation)
        # Only addons that already existed and changed version count as updated.
        changed = [
            addon
            for addon in after
            if addon.id in before and before[addon.id] != addon.installed_version
        ]
        logger.info(
            "update_all changed=%d %s",
            len(changed),
            ctx(installation=installation.id, engine=self.engine_id, operation="update_all"),
        )
        return changed

    async def remove(self, installation: WowInstallation, addon: Addon) -> None:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        if addon.provider == "unmanaged":
            raise AzerothAddonsError(
                ADDON_NOT_FOUND,
                "This addon is not managed by Azeroth Addons, so it will not be modified.",
                installation_id=installation.id,
                provider=addon.provider,
            )
        definition = definition_for(addon.provider, addon.provider_id)
        result = await self._adapter.remove(profile, definition)
        if not result.ok:
            raise self._adapter.failure(
                result,
                REMOVE_FAILED,
                f"Could not remove {addon.display_name}.",
                installation_id=installation.id,
                provider=addon.provider,
            )
        logger.info(
            "removed %s %s",
            definition,
            ctx(
                installation=installation.id,
                engine=self.engine_id,
                provider=addon.provider,
                operation="remove",
            ),
        )

    async def rollback(self, installation: WowInstallation, addon: Addon) -> Addon:
        if not self.capabilities().rollback:
            raise AzerothAddonsError(
                ENGINE_UNSUPPORTED,
                "Rollback is not enabled. Enable 'Experimental rollback' in Settings to use it.",
                installation_id=installation.id,
                engine=self.engine_id,
            )
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        definition = definition_for(addon.provider, addon.provider_id)
        result = await self._adapter.rollback(profile, definition)
        if not result.ok:
            raise self._adapter.failure(
                result,
                ROLLBACK_FAILED,
                f"Could not roll back {addon.display_name}.",
                installation_id=installation.id,
                provider=addon.provider,
            )
        rolled = await self._find_addon(installation, addon.provider, addon.provider_id)
        return rolled or addon

    # --- discovery ---------------------------------------------------------

    async def search(self, installation: WowInstallation, query: str, *, limit: int = 25) -> list[Addon]:
        await self._require_ready()
        profile = self._profile(installation)
        await self.ensure_profile(installation)
        result = await self._adapter.search(profile, query, limit=limit)
        if not result.ok:
            raise self._adapter.failure(
                result,
                SEARCH_FAILED,
                "The addon engine could not run that search.",
                installation_id=installation.id,
            )
        addons: list[Addon] = []
        for source, ident, name in parse_search_results(result.combined):
            addons.append(
                addon_from_engine(
                    provider=source_to_provider(source),
                    provider_id=ident,
                    version=None,
                    name=name or ident,
                )
            )
        return addons
