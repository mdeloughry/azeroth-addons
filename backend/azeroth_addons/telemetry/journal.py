"""The local error journal.

Every structured error the plugin produces is recorded here, **redacted at
ingestion** so sensitive text never even reaches the journal file. The journal
is bounded, deduplicates bursts of the same failure, and lives in the plugin's
settings directory next to the user's other data.

Recording is always on. Nothing leaves the device unless the separate,
opt-in reporter is enabled.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..logctx import get_logger
from ..settings import JsonStore
from .privacy import MAX_FIELD_CHARS, scrub, scrub_mapping

ERROR_JOURNAL_FILE = "error-journal.json"
JOURNAL_VERSION = 1
MAX_EVENTS = 200
DEDUPE_WINDOW_SECONDS = 60

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

SOURCE_BACKEND = "backend"
SOURCE_FRONTEND = "frontend"

logger = get_logger()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _seconds_between(first: str, second: str) -> float:
    try:
        left = _dt.datetime.fromisoformat(first)
        right = _dt.datetime.fromisoformat(second)
    except ValueError:
        return 0.0
    return abs((right - left).total_seconds())


def fingerprint_for(source: str, code: str, message: str) -> str:
    digest = hashlib.sha1(f"{source}|{code}|{message}".encode("utf-8", "replace")).hexdigest()
    return digest[:12]


MAX_FRAME_COUNT = 30


@dataclass
class ErrorEvent:
    code: str
    message: str
    source: str = SOURCE_BACKEND
    severity: str = SEVERITY_ERROR
    details: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    frames: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    count: int = 1

    def __post_init__(self) -> None:
        # Scrub on the way in: the journal on disk must already be safe to share.
        self.code = (self.code or "UNKNOWN").strip()[:80]
        self.message = (scrub(self.message) or "Unknown error")[:MAX_FIELD_CHARS]
        self.details = scrub(self.details)
        self.context = scrub_mapping(self.context or {})
        self.frames = _scrub_frames(self.frames)
        self.count = max(1, int(self.count))

    @property
    def fingerprint(self) -> str:
        return fingerprint_for(self.source, self.code, self.message)

    @property
    def id(self) -> str:
        digest = hashlib.sha1(f"{self.fingerprint}|{self.timestamp}".encode("utf-8", "replace")).hexdigest()
        return digest[:12]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "count": self.count,
        }
        if self.details:
            payload["details"] = self.details
        if self.context:
            payload["context"] = self.context
        if self.frames:
            payload["frames"] = self.frames
        return payload

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "ErrorEvent":
        frames = record.get("frames")
        return cls(
            code=str(record.get("code") or "UNKNOWN"),
            message=str(record.get("message") or ""),
            source=str(record.get("source") or SOURCE_BACKEND),
            severity=str(record.get("severity") or SEVERITY_ERROR),
            details=record.get("details"),
            context=dict(record.get("context") or {}),
            frames=[dict(frame) for frame in frames if isinstance(frame, Mapping)] if isinstance(frames, list) else [],
            timestamp=str(record.get("timestamp") or _now()),
            count=int(record.get("count") or 1),
        )

    @classmethod
    def build(
        cls,
        *,
        code: str,
        message: str,
        details: str | None = None,
        source: str = SOURCE_BACKEND,
        severity: str = SEVERITY_ERROR,
        frames: list[dict[str, Any]] | None = None,
        **context: Any,
    ) -> "ErrorEvent":
        return cls(
            code=code,
            message=message,
            details=details,
            source=source,
            severity=severity,
            context={key: value for key, value in context.items() if value not in (None, "", False)},
            frames=list(frames or []),
        )


def _scrub_frames(frames: list[Any]) -> list[dict[str, Any]]:
    """Keep the useful shape of a traceback, with every string scrubbed."""
    cleaned: list[dict[str, Any]] = []
    for frame in list(frames)[-MAX_FRAME_COUNT:]:
        if not isinstance(frame, Mapping):
            continue
        entry: dict[str, Any] = {}
        for key in ("filename", "function", "line"):
            value = frame.get(key)
            if value in (None, ""):
                continue
            entry[key] = scrub(str(value))
        lineno = frame.get("lineno")
        if isinstance(lineno, int) and lineno > 0:
            entry["lineno"] = lineno
        if entry:
            cleaned.append(entry)
    return cleaned


class ErrorJournal:
    def __init__(
        self,
        store: JsonStore,
        *,
        limit: int = MAX_EVENTS,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._store = store
        self._limit = max(1, limit)
        self._on_event = on_event
        self._events: list[ErrorEvent] = []
        self._load()

    # --- persistence -------------------------------------------------------

    def _load(self) -> None:
        raw = self._store.read(ERROR_JOURNAL_FILE, {})
        records: list[Any] = []
        if isinstance(raw, dict):
            found = raw.get("events")
            if isinstance(found, list):
                records = found
        elif isinstance(raw, list):
            records = raw

        events: list[ErrorEvent] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            try:
                events.append(ErrorEvent.from_dict(record))
            except Exception as exc:  # noqa: BLE001 - a bad record must not break startup
                logger.debug("skipping malformed journal record: %s", exc)
        self._events = events[: self._limit]

    def _save(self) -> None:
        self._store.write(
            ERROR_JOURNAL_FILE,
            {"version": JOURNAL_VERSION, "events": [event.to_dict() for event in self._events]},
        )

    # --- recording ---------------------------------------------------------

    def record(self, event: ErrorEvent) -> dict[str, Any]:
        """Store an event (or bump a recent duplicate) and return its payload."""
        if self._events:
            newest = self._events[0]
            if (
                newest.fingerprint == event.fingerprint
                and _seconds_between(newest.timestamp, event.timestamp) <= DEDUPE_WINDOW_SECONDS
            ):
                newest.count += event.count
                newest.timestamp = event.timestamp
                self._save()
                payload = newest.to_dict()
                self._notify(payload)
                return payload

        self._events.insert(0, event)
        del self._events[self._limit :]
        self._save()
        payload = event.to_dict()
        self._notify(payload)
        return payload

    def _notify(self, payload: dict[str, Any]) -> None:
        """Hand the payload to the (optional) reporter without ever raising."""
        if self._on_event is None:
            return
        try:
            self._on_event(payload)
        except Exception as exc:  # noqa: BLE001 - reporting must not break recording
            logger.debug("error journal sink failed: %s", exc)

    # --- reads -------------------------------------------------------------

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events[: max(1, limit)]]

    def latest(self) -> dict[str, Any] | None:
        return self._events[0].to_dict() if self._events else None

    def clear(self) -> None:
        self._events = []
        self._save()

    def summary(self) -> dict[str, Any]:
        by_code: dict[str, int] = {}
        for event in self._events:
            by_code[event.code] = by_code.get(event.code, 0) + event.count
        return {
            "stored": len(self._events),
            "total": sum(event.count for event in self._events),
            "distinctCodes": len(by_code),
            "byCode": dict(sorted(by_code.items(), key=lambda item: -item[1])[:10]),
            "lastAt": self._events[0].timestamp if self._events else None,
        }
