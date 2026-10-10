"""Sentry protocol support.

Azeroth Addons talks the Sentry **Store API** directly instead of using the
official SDK, because the backend must stay stdlib-only (a Decky plugin cannot
install Python packages).

Speaking the protocol rather than a bespoke schema means reports land in any
proven, Sentry-compatible tool with no extra work on either side:

* **GlitchTip** (self-hosted, MIT) - the recommended destination;
* **Bugsink** (self-hosted, single container);
* **Sentry** (self-hosted or SaaS).

The DSN is a *client-side* identifier designed to be embedded in clients, but
it is still treated as sensitive here: it is never logged and the UI displays
only a keyless form of it.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from .. import __version__
from .privacy import scrub, scrub_mapping

CLIENT_NAME = "azeroth-addons"
CLIENT_VERSION = __version__
SENTRY_PROTOCOL_VERSION = "7"
STORE_PATH_TEMPLATE = "/api/{project_id}/store/"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

DSN_PATTERN = re.compile(
    r"^(?P<scheme>https?)://(?P<key>[^@\s]+)@(?P<host>[^/\s]+)/(?P<project>\d+)$"
)


@dataclass(frozen=True)
class SentryDsn:
    scheme: str
    public_key: str
    host: str
    project_id: str

    @classmethod
    def parse(cls, dsn: str | None) -> "SentryDsn | None":
        match = DSN_PATTERN.match((dsn or "").strip())
        if not match:
            return None
        return cls(
            scheme=match.group("scheme"),
            public_key=match.group("key"),
            host=match.group("host"),
            project_id=match.group("project"),
        )

    @property
    def store_url(self) -> str:
        return f"{self.scheme}://{self.host}{STORE_PATH_TEMPLATE.format(project_id=self.project_id)}"

    @property
    def display(self) -> str:
        """A safe representation for the UI and logs: the key is never shown."""
        return f"{self.scheme}://{self.host}/{self.project_id}"

    def is_loopback(self) -> bool:
        host = self.host.split(":", 1)[0]
        return host in LOOPBACK_HOSTS


def validate_dsn(dsn: str | None) -> str | None:
    """Return a human reason when the DSN is unusable, else ``None``."""
    candidate = (dsn or "").strip()
    if not candidate:
        return "A Sentry DSN is required."
    parsed = SentryDsn.parse(candidate)
    if parsed is None:
        return "That does not look like a Sentry DSN (expected https://key@host/project)."
    if parsed.scheme == "http" and not parsed.is_loopback():
        return "Plain HTTP is only allowed for a local address."
    if not parsed.host or urlparse(f"{parsed.scheme}://{parsed.host}").hostname is None:
        return "The DSN host is not valid."
    return None


def auth_header(dsn: SentryDsn) -> str:
    return (
        f"Sentry sentry_version={SENTRY_PROTOCOL_VERSION}, "
        f"sentry_client={CLIENT_NAME}/{CLIENT_VERSION}, "
        f"sentry_key={dsn.public_key}"
    )


def _frames_to_stacktrace(frames: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Convert our captured frames into Sentry frames (oldest call first)."""
    sentry_frames: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        filename = scrub(str(frame.get("filename") or "<unknown>")) or "<unknown>"
        entry: dict[str, Any] = {
            "filename": filename,
            "abs_path": filename,
            "function": str(frame.get("function") or "<unknown>"),
            "in_app": True,
        }
        lineno = frame.get("lineno")
        if isinstance(lineno, int) and lineno > 0:
            entry["lineno"] = lineno
        line = frame.get("line")
        if line:
            entry["context_line"] = scrub(str(line))
        sentry_frames.append(entry)
    return {"frames": sentry_frames}


def build_event(
    event: Mapping[str, Any],
    *,
    plugin_version: str = __version__,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one journal event as a Sentry event document."""
    code = str(event.get("code") or "UNKNOWN")
    message = scrub(str(event.get("message") or "")) or code
    source = str(event.get("source") or "backend")
    severity = str(event.get("severity") or "error")
    context = scrub_mapping(event.get("context") or {})
    frames = list(event.get("frames") or [])

    tags: dict[str, Any] = {"app": "azeroth-addons", "source": source, "code": code}
    # Context keys become tags so they are filterable in the tracking UI.
    for key in ("engine", "provider", "installation", "operation"):
        value = context.get(key)
        if value:
            tags[key] = value

    extra: dict[str, Any] = {"fingerprint": event.get("fingerprint"), "count": event.get("count")}
    if event.get("details"):
        extra["details"] = event["details"]
    for key, value in context.items():
        if key not in tags:
            extra[key] = value
    if runtime:
        extra["runtime"] = dict(runtime)

    payload: dict[str, Any] = {
        "event_id": uuid.uuid4().hex,
        "timestamp": time.time(),
        "platform": "javascript" if source == "frontend" else "python",
        "level": "warning" if severity == "warning" else "error",
        "logger": "azeroth-addons",
        "release": f"azeroth-addons@{plugin_version}",
        "environment": "production",
        "sdk": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        "message": {"formatted": message},
        "tags": {key: value for key, value in tags.items() if value},
        "extra": {key: value for key, value in extra.items() if value not in (None, "", {})},
        "fingerprint": ["{{ default }}"],
        "exception": {
            "values": [
                {
                    "type": code,
                    "value": message,
                    "mechanism": {"type": "generic", "handled": True},
                    "stacktrace": _frames_to_stacktrace(frames),
                }
            ]
        },
    }

    operation = context.get("operation")
    if operation:
        payload["transaction"] = str(operation)
    return payload
