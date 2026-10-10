"""Structured errors and the RPC result envelope.

Every backend operation that crosses the RPC boundary returns either
``{"ok": True, "data": ...}`` or ``{"ok": False, "error": {...}}``.
Exceptions never escape raw, so the frontend always receives a code it can act on.
"""

from __future__ import annotations

import functools
import linecache
import traceback
from typing import Any, Awaitable, Callable, Mapping, TypeVar

from .logctx import get_logger

# --- WoW / installation ----------------------------------------------------
WOW_NOT_FOUND = "WOW_NOT_FOUND"
WOW_RUNNING = "WOW_RUNNING"
INSTALLATION_UNAVAILABLE = "INSTALLATION_UNAVAILABLE"
INSTALLATION_NOT_FOUND = "INSTALLATION_NOT_FOUND"
INVALID_WOW_PATH = "INVALID_WOW_PATH"
DUPLICATE_INSTALLATION = "DUPLICATE_INSTALLATION"

# --- engine ----------------------------------------------------------------
ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
ENGINE_UNSUPPORTED = "ENGINE_UNSUPPORTED"
ENGINE_FAILED = "ENGINE_FAILED"
INSTAWOW_MISSING = "INSTAWOW_MISSING"
INSTAWOW_INCOMPATIBLE = "INSTAWOW_INCOMPATIBLE"

# --- provider --------------------------------------------------------------
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
PROVIDER_BAD_RESPONSE = "PROVIDER_BAD_RESPONSE"

# --- operations ------------------------------------------------------------
INSTALL_FAILED = "INSTALL_FAILED"
UPDATE_FAILED = "UPDATE_FAILED"
REMOVE_FAILED = "REMOVE_FAILED"
ROLLBACK_FAILED = "ROLLBACK_FAILED"
RECONCILE_FAILED = "RECONCILE_FAILED"
SEARCH_FAILED = "SEARCH_FAILED"
ADDON_NOT_FOUND = "ADDON_NOT_FOUND"

# --- infrastructure --------------------------------------------------------
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
NETWORK_ERROR = "NETWORK_ERROR"
FILESYSTEM_ERROR = "FILESYSTEM_ERROR"
SECURITY_VIOLATION = "SECURITY_VIOLATION"
CONFIG_ERROR = "CONFIG_ERROR"
NOT_READY = "NOT_READY"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
INTERNAL_ERROR = "INTERNAL_ERROR"


class AzerothAddonsError(Exception):
    """A structured, user-presentable error.

    ``details`` is for developers/logs; ``message`` is safe to show to users.
    Never place credentials in either field.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: str | None = None,
        installation_id: str | None = None,
        provider: str | None = None,
        engine: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.installation_id = installation_id
        self.provider = provider
        self.engine = engine

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        if self.installation_id:
            payload["installationId"] = self.installation_id
        if self.provider:
            payload["provider"] = self.provider
        if self.engine:
            payload["engine"] = self.engine
        return payload

    def with_context(
        self,
        *,
        installation_id: str | None = None,
        provider: str | None = None,
        engine: str | None = None,
    ) -> "AzerothAddonsError":
        if installation_id and not self.installation_id:
            self.installation_id = installation_id
        if provider and not self.provider:
            self.provider = provider
        if engine and not self.engine:
            self.engine = engine
        return self

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AzerothAddonsError(code={self.code!r}, message={self.message!r})"


def ok(data: Any = None) -> dict[str, Any]:
    """Success envelope."""
    return {"ok": True, "data": data}


def fail(error: AzerothAddonsError | Exception) -> dict[str, Any]:
    """Failure envelope."""
    if not isinstance(error, AzerothAddonsError):
        error = AzerothAddonsError(INTERNAL_ERROR, str(error) or "Unexpected error")
    return {"ok": False, "error": error.to_dict()}


T = TypeVar("T")

# --- error sink -------------------------------------------------------------
#
# The journal lives in :mod:`telemetry`; ``errors`` must not depend on it, so the
# application installs a sink at startup. A failing sink can never break a call.

ErrorSink = Callable[[Mapping[str, Any]], None]

_error_sink: ErrorSink | None = None


def set_error_sink(sink: ErrorSink | None) -> None:
    """Install (or clear) the destination for every recorded error."""
    global _error_sink
    _error_sink = sink


def _emit_to_sink(fields: Mapping[str, Any]) -> None:
    if _error_sink is None:
        return
    try:
        _error_sink(fields)
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break a call
        get_logger().debug("error sink failed: %s", exc)


def _source_line(tb: Any) -> str | None:
    try:
        line = linecache.getline(tb.tb_frame.f_code.co_filename, tb.tb_lineno, tb.tb_frame.f_globals)
    except Exception:  # noqa: BLE001 - source may be unavailable
        return None
    return line.strip() or None


def extract_frames(exc: BaseException) -> list[dict[str, Any]]:
    """Capture a traceback as structured frames for error tracking."""
    frames: list[dict[str, Any]] = []
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append(
            {
                "filename": code.co_filename,
                "lineno": tb.tb_lineno,
                "function": code.co_name,
                "line": _source_line(tb),
            }
        )
        tb = tb.tb_next
    return frames


def rpc(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Wrap a plugin method so it always returns an envelope and never raises."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        logger = get_logger()
        name = fn.__name__
        try:
            return ok(await fn(*args, **kwargs))
        except AzerothAddonsError as exc:
            logger.warning("rpc %s failed: %s (%s)", name, exc.message, exc.code)
            _emit_to_sink(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "context": {
                        "operation": name,
                        "installation": exc.installation_id,
                        "provider": exc.provider,
                        "engine": exc.engine,
                    },
                }
            )
            return fail(exc)
        except Exception as exc:  # noqa: BLE001 - boundary guard by design
            logger.error("rpc %s crashed: %s", name, exc)
            logger.debug("rpc %s traceback:\n%s", name, traceback.format_exc())
            _emit_to_sink(
                {
                    "code": INTERNAL_ERROR,
                    "message": "An unexpected internal error occurred.",
                    "details": f"{type(exc).__name__}: {exc}",
                    "context": {"operation": name},
                    "frames": extract_frames(exc),
                }
            )
            return fail(
                AzerothAddonsError(
                    INTERNAL_ERROR,
                    "An unexpected internal error occurred.",
                    details=f"{type(exc).__name__}: {exc}",
                )
            )

    return wrapper


def error_from_process_failure(
    code: str,
    message: str,
    *,
    returncode: int | None,
    stderr: str,
    **context: Any,
) -> AzerothAddonsError:
    """Build an error from a failed subprocess, keeping stderr only in details."""
    tail = _tail(stderr)
    details = f"exit={returncode}"
    if tail:
        details = f"{details}\n{_redact_process_output(tail)}"
    return AzerothAddonsError(code, message, details=details, **context)


def _tail(text: str, limit: int = 4000) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "...\n" + text[-limit:]


_SENSITIVE_MARKERS = ("api-key", "apikey", "api_key", "authorization", "bearer ", "token")


def _redact_process_output(text: str) -> str:
    """Best-effort redaction of anything token-shaped in captured stderr."""
    import re

    redacted = text
    for marker in _SENSITIVE_MARKERS:
        redacted = re.sub(
            rf"(?i)({re.escape(marker)}[^:]*:\s*)\S+",
            r"\1<redacted>",
            redacted,
        )
    return redacted
