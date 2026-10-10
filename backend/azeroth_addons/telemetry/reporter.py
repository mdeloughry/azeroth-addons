"""Opt-in error reporting.

**Off by default. Nothing is ever sent until the user turns it on and supplies
a destination.**

Two destinations are supported:

* ``sentry`` (default) - the Sentry **Store API**, which is what proven,
  Sentry-compatible tools speak: GlitchTip, Bugsink, Sentry itself.
* ``custom`` - a plain JSON POST of the documented journal event, for anything
  else that accepts a webhook.

Privacy properties, all covered by tests:

* the destination must be HTTPS (plain HTTP is allowed only for loopback);
* only redacted journal entries are sent - see :mod:`privacy`;
* no device identifier, hostname, username or absolute path is included;
* stack frames are rewritten relative to the plugin, with every string scrubbed;
* the exact request body is previewable before reporting is enabled;
* sends are rate limited, and a failing destination is surfaced in the UI
  instead of being retried in a loop;
* a failed send never affects the operation that produced the error.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Callable, Mapping

from .. import __version__
from ..logctx import get_logger
from ..settings import SettingsStore
from .journal import SOURCE_BACKEND, ErrorEvent
from .privacy import scrub_mapping
from .sentry import (
    SentryDsn,
    auth_header,
    build_event as build_sentry_event,
    validate_dsn,
)

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 10.0
MAX_SENDS_PER_HOUR = 20
IDENTICAL_COOLDOWN_SECONDS = 3600
MAX_RESPONSE_BYTES = 4096
USER_AGENT = f"AzerothAddons/{__version__} (opt-in error reporting)"

FORMAT_SENTRY = "sentry"
FORMAT_CUSTOM = "custom"
FORMATS = (FORMAT_SENTRY, FORMAT_CUSTOM)

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

logger = get_logger()

RuntimeProvider = Callable[[], Mapping[str, Any]]


def validate_endpoint(url: str) -> str | None:
    """Return a human reason when a plain-JSON endpoint is unusable, else ``None``."""
    candidate = (url or "").strip()
    if not candidate:
        return "No endpoint is configured."
    try:
        parsed = urllib.parse.urlparse(candidate)
    except ValueError:
        return "That URL could not be parsed."
    if parsed.scheme not in ("https", "http"):
        return "The endpoint must be an https:// URL."
    if not parsed.netloc or parsed.hostname is None:
        return "The endpoint is missing a host."
    if parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS:
        return "Plain HTTP is only allowed for a local address."
    return None


class ErrorReporter:
    def __init__(
        self,
        settings: SettingsStore,
        *,
        runtime_provider: RuntimeProvider | None = None,
        plugin_version: str = __version__,
        timeout: float = DEFAULT_TIMEOUT,
        max_per_hour: int = MAX_SENDS_PER_HOUR,
    ) -> None:
        self._settings = settings
        self._runtime_provider = runtime_provider or (lambda: {})
        self._plugin_version = plugin_version
        self._timeout = timeout
        self._max_per_hour = max_per_hour

        self._send_times: deque[float] = deque()
        self._fingerprint_sent_at: dict[str, float] = {}
        self._sent = 0
        self._failed = 0
        self._last_sent_at: str | None = None
        self._last_error: str | None = None

    # --- configuration -----------------------------------------------------

    def enabled(self) -> bool:
        return bool(self._settings.get("enableErrorReporting", False))

    def format(self) -> str:
        value = str(self._settings.get("errorReportingFormat") or FORMAT_SENTRY).strip().lower()
        return value if value in FORMATS else FORMAT_SENTRY

    def dsn(self) -> str:
        """The DSN is held as a credential, not in plain settings."""
        return str(self._settings.credential("sentry") or "").strip()

    def endpoint(self) -> str:
        return str(self._settings.get("errorReportingEndpoint") or "").strip()

    def destination_display(self) -> str:
        """What the UI shows. Never includes a credential."""
        if self.format() == FORMAT_SENTRY:
            parsed = SentryDsn.parse(self.dsn())
            return parsed.display if parsed else ""
        return self.endpoint()

    def configuration_problem(self) -> str | None:
        if self.format() == FORMAT_SENTRY:
            return validate_dsn(self.dsn())
        return validate_endpoint(self.endpoint())

    def usable(self) -> bool:
        return self.enabled() and self.configuration_problem() is None

    # --- payloads ----------------------------------------------------------

    def runtime(self) -> dict[str, Any]:
        try:
            info = dict(self._runtime_provider() or {})
        except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
            logger.debug("runtime provider failed: %s", exc)
            info = {}
        return scrub_mapping(info)

    def build_request(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """The exact request that would be sent: url, headers and body."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.format() == FORMAT_SENTRY:
            parsed = SentryDsn.parse(self.dsn())
            if parsed is None:
                raise ValueError("invalid Sentry DSN")
            body = build_sentry_event(event, plugin_version=self._plugin_version, runtime=self.runtime())
            headers["X-Sentry-Auth"] = auth_header(parsed)
            return {"url": parsed.store_url, "headers": headers, "body": body}

        body = {
            "schema": SCHEMA_VERSION,
            "plugin": {"name": "Azeroth Addons", "version": self._plugin_version},
            "runtime": self.runtime(),
            "event": dict(event),
        }
        return {"url": self.endpoint(), "headers": headers, "body": body}

    def preview(self) -> dict[str, Any]:
        """Show precisely what a report looks like, with credentials masked."""
        sample = ErrorEvent.build(
            code="PREVIEW_EVENT",
            message="This is a sample event showing exactly what would be sent.",
            details=(
                "Error details are included after credential redaction, with "
                "usernames removed from paths and plugin paths rewritten relative."
            ),
            source=SOURCE_BACKEND,
            installation="retail-1a2b3c",
            engine="instawow",
            operation="update",
        ).to_dict()

        request: dict[str, Any] | None = None
        problem = self.configuration_problem()
        if problem is None:
            try:
                request = self.build_request(sample)
            except ValueError:
                request = None

        if request is not None:
            masked = dict(request["headers"])
            for key, value in masked.items():
                if key.lower() == "x-sentry-auth":
                    masked[key] = _mask_sentry_auth(str(value))
            request = {"url": request["url"], "headers": masked, "body": request["body"]}

        return {
            "schemaVersion": SCHEMA_VERSION,
            "format": self.format(),
            "enabled": self.enabled(),
            "destination": self.destination_display(),
            "problem": problem,
            "request": request,
        }

    # --- sending -----------------------------------------------------------

    def _rate_limit_reason(self, fingerprint: str) -> str | None:
        now = time.monotonic()
        self._send_times = deque(when for when in self._send_times if now - when < 3600)
        if len(self._send_times) >= self._max_per_hour:
            return f"Rate limited to {self._max_per_hour} reports per hour."
        last_same = self._fingerprint_sent_at.get(fingerprint)
        if last_same is not None and now - last_same < IDENTICAL_COOLDOWN_SECONDS:
            return "That same error was already reported in the last hour."
        return None

    async def maybe_send(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Send one event if reporting is on. Never raises."""
        if not self.enabled():
            return {"sent": False, "reason": "disabled"}

        problem = self.configuration_problem()
        if problem:
            return {"sent": False, "reason": problem}

        limited = self._rate_limit_reason(str(event.get("fingerprint") or ""))
        if limited:
            return {"sent": False, "reason": limited}

        return await self._send(event, fingerprint=str(event.get("fingerprint") or "") or None)

    async def send_test(self) -> dict[str, Any]:
        """Send a marked test event, bypassing the enabled flag and cooldown."""
        problem = self.configuration_problem()
        if problem:
            return {"sent": False, "reason": problem}
        event = ErrorEvent.build(
            code="TEST_REPORT",
            message="Test report from Azeroth Addons. Nothing is wrong.",
            details="This confirms the configured destination accepts reports.",
            source=SOURCE_BACKEND,
            operation="send_test",
        ).to_dict()
        return await self._send(event, fingerprint=None)

    async def _send(self, event: Mapping[str, Any], fingerprint: str | None) -> dict[str, Any]:
        try:
            request = self.build_request(event)
        except Exception as exc:  # noqa: BLE001 - configuration problem, not a crash
            return self._record_failure(str(exc) or "Invalid reporting configuration")

        started = time.monotonic()
        try:
            status = await asyncio.to_thread(
                self._post_sync, str(request["url"]), dict(request["headers"]), request["body"]
            )
        except urllib.error.HTTPError as exc:
            return self._record_failure(f"HTTP {exc.code}")
        except urllib.error.URLError as exc:
            return self._record_failure(f"Could not reach the destination ({exc.reason})")
        except Exception as exc:  # noqa: BLE001 - reporting is best effort
            return self._record_failure(str(exc) or exc.__class__.__name__)

        self._send_times.append(time.monotonic())
        if fingerprint:
            self._fingerprint_sent_at[fingerprint] = time.monotonic()
        self._sent += 1
        self._last_sent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._last_error = None
        logger.debug("error report delivered status=%s in %dms", status, int((time.monotonic() - started) * 1000))
        return {"sent": True, "status": status}

    def _post_sync(self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]) -> int:
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        # The destination is never logged: a DSN or webhook path may be secret.
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310 - user-configured destination
            response.read(MAX_RESPONSE_BYTES)
            return int(response.status)

    def _record_failure(self, reason: str) -> dict[str, Any]:
        self._failed += 1
        self._last_error = reason
        logger.debug("error report not delivered: %s", reason)
        return {"sent": False, "reason": reason}

    # --- status ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        problem = self.configuration_problem()
        return {
            "enabled": self.enabled(),
            "usable": self.usable(),
            "format": self.format(),
            "formats": list(FORMATS),
            "destination": self.destination_display(),
            "problem": problem,
            "schemaVersion": SCHEMA_VERSION,
            "sent": self._sent,
            "failed": self._failed,
            "lastSentAt": self._last_sent_at,
            "lastError": self._last_error,
            "maxPerHour": self._max_per_hour,
            "sendsThisHour": len(self._send_times),
        }


def _mask_sentry_auth(value: str) -> str:
    """Hide the DSN key inside an X-Sentry-Auth header for display."""
    parts = [part.strip() for part in value.split(",")]
    masked = []
    for part in parts:
        if part.startswith("sentry_key="):
            masked.append("sentry_key=<redacted>")
        else:
            masked.append(part)
    return ", ".join(masked)
