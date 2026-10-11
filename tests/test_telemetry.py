"""Tests for diagnostics and opt-in error reporting.

The privacy guarantees are the point of this module: redaction, the
everything-off-by-default posture, and the fact that nothing is transmitted
until the user opts in (a destination is built in, so there is nothing to
configure).
"""

from __future__ import annotations

import json
import os
import urllib.error
from pathlib import Path

import pytest

from azeroth_addons.settings import JsonStore, SettingsStore
from azeroth_addons.telemetry import privacy
from azeroth_addons.telemetry.journal import ErrorEvent, ErrorJournal
from azeroth_addons.telemetry.reporter import (
    DEFAULT_SENTRY_DSN,
    FORMAT_CUSTOM,
    FORMAT_SENTRY,
    ErrorReporter,
    validate_endpoint,
)
from azeroth_addons.telemetry.sentry import (
    SentryDsn,
    auth_header,
    build_event,
    validate_dsn,
)

DSN = "https://abc123def456@glitchtip.example.com/42"


def make_settings(tmp_path: Path, **values) -> SettingsStore:
    store = JsonStore(tmp_path / "settings")
    settings = SettingsStore(store)
    settings.load()
    if values:
        settings.update(values)
    return settings


def enable_sentry(settings: SettingsStore, dsn: str = DSN) -> None:
    """Turn reporting on with a Sentry destination (the DSN is a credential)."""
    settings.update({"enableErrorReporting": True, "errorReportingFormat": FORMAT_SENTRY})
    settings.set_credential("sentry", dsn)


@pytest.fixture
def reporter_env(tmp_path: Path):
    settings = make_settings(tmp_path)
    reporter = ErrorReporter(
        settings,
        runtime_provider=lambda: {"python": "3.11.7", "platform": "Linux x86_64", "engine": "instawow 7.2.1"},
    )
    return reporter, settings


# --- privacy ----------------------------------------------------------------


def test_scrub_removes_the_home_directory(monkeypatch, tmp_path: Path):
    home = tmp_path / "home" / "deck"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert privacy.scrub(f"failed to read {home}/World of Warcraft") == "failed to read ~/World of Warcraft"


def test_scrub_removes_usernames_outside_the_home_directory(monkeypatch, tmp_path: Path):
    home = tmp_path / "home" / "deck"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    scrubbed = privacy.scrub("mounted at /run/media/deck/SDCARD/World of Warcraft")
    assert "deck" not in scrubbed
    assert "/run/media/<user>/SDCARD/World of Warcraft" in scrubbed


def test_scrub_removes_credentials():
    scrubbed = privacy.scrub("x-api-key: super-secret-value used for the request")
    assert "super-secret-value" not in scrubbed


def test_scrub_keeps_prose_intact(monkeypatch, tmp_path: Path):
    """Bare words are never replaced - 'Steam Deck' must survive."""
    home = tmp_path / "home" / "deck"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert privacy.scrub("Steam Deck plugins live under decky") == "Steam Deck plugins live under decky"


def test_scrub_relativises_plugin_paths(tmp_path: Path):
    plugin = tmp_path / "plugins" / "azeroth-addons"
    backend = plugin / "backend" / "azeroth_addons"
    backend.mkdir(parents=True)
    privacy.configure(plugin_root=plugin)
    try:
        scrubbed = privacy.scrub(f'File "{backend}/errors.py", line 42')
        assert str(plugin) not in scrubbed
        assert "backend/azeroth_addons/errors.py" in scrubbed
    finally:
        privacy.configure(plugin_root=None)


def test_scrub_truncates_runaway_text():
    scrubbed = privacy.scrub("x" * 20_000)
    assert scrubbed is not None
    assert len(scrubbed) < 20_000
    assert "truncated" in scrubbed


def test_scrub_mapping_drops_sensitive_values():
    cleaned = privacy.scrub_mapping(
        {
            "apiKey": "secret-value",
            "token": "secret-value",
            "installation": "retail-1a2b3c",
            "empty": "",
            "nested": {"authorization": "Bearer xyz", "engine": "instawow"},
        }
    )
    assert cleaned["apiKey"] == "<redacted>"
    assert cleaned["token"] == "<redacted>"
    assert "empty" not in cleaned
    assert cleaned["installation"] == "retail-1a2b3c"
    assert cleaned["nested"]["authorization"] == "<redacted>"
    assert cleaned["nested"]["engine"] == "instawow"


# --- journal ----------------------------------------------------------------


def test_journal_records_and_persists(tmp_path: Path):
    store = JsonStore(tmp_path / "settings")
    journal = ErrorJournal(store)
    journal.record(ErrorEvent.build(code="UPDATE_FAILED", message="boom", installation="retail-1a2b3c"))

    reloaded = ErrorJournal(store)
    events = reloaded.events()
    assert len(events) == 1
    assert events[0]["code"] == "UPDATE_FAILED"
    assert events[0]["context"]["installation"] == "retail-1a2b3c"
    assert events[0]["count"] == 1


def test_journal_scrubs_at_ingestion(tmp_path: Path, monkeypatch):
    home = tmp_path / "home" / "deck"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    store = JsonStore(tmp_path / "settings")
    journal = ErrorJournal(store)
    journal.record(
        ErrorEvent.build(
            code="FILESYSTEM_ERROR",
            message=f"could not write {home}/addons",
            details="api_key: super-secret",
            installation="retail-1a2b3c",
        )
    )
    raw = store.path("error-journal.json").read_text()
    assert str(home) not in raw
    assert "super-secret" not in raw
    assert "~/addons" in raw


def test_journal_folds_repeated_failures_together(tmp_path: Path):
    journal = ErrorJournal(JsonStore(tmp_path / "settings"))
    for _ in range(5):
        journal.record(ErrorEvent.build(code="UPDATE_FAILED", message="boom"))
    assert len(journal.events()) == 1
    assert journal.events()[0]["count"] == 5


def test_journal_is_bounded(tmp_path: Path):
    journal = ErrorJournal(JsonStore(tmp_path / "settings"), limit=10)
    for index in range(25):
        journal.record(ErrorEvent.build(code="CODE", message=f"failure {index}"))
    events = journal.events(limit=100)
    assert len(events) == 10
    assert events[0]["message"] == "failure 24"  # newest first


def test_journal_summary_and_clear(tmp_path: Path):
    journal = ErrorJournal(JsonStore(tmp_path / "settings"))
    journal.record(ErrorEvent.build(code="A", message="one"))
    journal.record(ErrorEvent.build(code="B", message="two"))
    summary = journal.summary()
    assert summary["stored"] == 2
    assert summary["distinctCodes"] == 2
    assert summary["byCode"]["A"] == 1
    journal.clear()
    assert journal.events() == []
    assert journal.summary()["stored"] == 0


def test_journal_scrubs_stack_frames(tmp_path: Path):
    journal = ErrorJournal(JsonStore(tmp_path / "settings"))
    journal.record(
        ErrorEvent.build(
            code="INTERNAL_ERROR",
            message="crash",
            frames=[{"filename": "/etc/shadow", "function": "f", "lineno": 3, "line": "token = 'abc'"}],
        )
    )
    frames = journal.events()[0]["frames"]
    assert frames[0]["lineno"] == 3
    assert len(frames[0]["filename"]) <= len("/etc/shadow")


# --- sentry protocol --------------------------------------------------------


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("https://abc@glitchtip.example.com/42", ("https", "abc", "glitchtip.example.com", "42")),
        ("http://key@localhost:8000/1", ("http", "key", "localhost:8000", "1")),
    ],
)
def test_dsn_parsing(dsn, expected):
    parsed = SentryDsn.parse(dsn)
    assert parsed is not None
    assert (parsed.scheme, parsed.public_key, parsed.host, parsed.project_id) == expected


@pytest.mark.parametrize("dsn", ["", "not-a-dsn", "https://glitchtip.example.com/42", "sentry.io/42"])
def test_dsn_rejects_malformed_values(dsn):
    assert SentryDsn.parse(dsn) is None
    assert validate_dsn(dsn) is not None


def test_dsn_requires_https_unless_loopback():
    assert validate_dsn("https://key@glitchtip.example.com/42") is None
    assert validate_dsn("http://key@localhost:8000/1") is None
    assert "Plain HTTP" in (validate_dsn("http://key@glitchtip.example.com/42") or "")


def test_dsn_display_hides_the_key():
    parsed = SentryDsn.parse(DSN)
    assert parsed is not None
    assert "abc123def456" not in parsed.display
    assert parsed.display == "https://glitchtip.example.com/42"


def test_auth_header_uses_the_protocol():
    parsed = SentryDsn.parse(DSN)
    assert parsed is not None
    header = auth_header(parsed)
    assert header.startswith("Sentry sentry_version=")
    assert "sentry_client=azeroth-addons/" in header
    assert "sentry_key=abc123def456" in header


def test_build_event_shape():
    event = ErrorEvent.build(
        code="UPDATE_FAILED",
        message="Could not update Masque.",
        details="exit=1",
        installation="retail-1a2b3c",
        engine="instawow",
        provider="curseforge",
        operation="update_addon",
        frames=[{"filename": "backend/azeroth_addons/engines/instawow.py", "function": "update", "lineno": 7}],
    ).to_dict()
    payload = build_event(event, runtime={"python": "3.11.7"})

    assert payload["platform"] == "python"
    assert payload["level"] == "error"
    assert payload["release"].startswith("azeroth-addons@")
    assert len(payload["event_id"]) == 32
    assert payload["tags"]["code"] == "UPDATE_FAILED"
    assert payload["tags"]["engine"] == "instawow"
    assert payload["tags"]["installation"] == "retail-1a2b3c"
    assert payload["transaction"] == "update_addon"
    assert payload["message"]["formatted"] == "Could not update Masque."
    exception = payload["exception"]["values"][0]
    assert exception["type"] == "UPDATE_FAILED"
    frames = exception["stacktrace"]["frames"]
    assert frames[0]["filename"].endswith("engines/instawow.py")
    assert frames[0]["in_app"] is True


def test_frontend_events_are_tagged_as_javascript():
    event = ErrorEvent.build(code="UI_CRASH", message="render failed", source="frontend").to_dict()
    payload = build_event(event)
    assert payload["platform"] == "javascript"
    assert payload["tags"]["source"] == "frontend"


def test_built_event_never_leaks_a_home_path(monkeypatch, tmp_path: Path):
    home = tmp_path / "home" / "deck"
    addons = home / "plugins"
    addons.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    event = ErrorEvent.build(
        code="FILESYSTEM_ERROR",
        message=f"cannot write {addons}/Interface/AddOns",
        details=f"path={addons}/x token=abc:secret",
        installation="retail-1a2b3c",
    ).to_dict()
    serialised = json.dumps(build_event(event))
    assert str(home) not in serialised
    assert "abc:secret" not in serialised


# --- reporter ---------------------------------------------------------------


def test_reporting_is_off_by_default(reporter_env):
    reporter, _settings = reporter_env
    assert reporter.enabled() is False
    assert reporter.usable() is False
    assert reporter.status()["sent"] == 0
    # A built-in destination is present but unused until the user opts in.
    assert reporter.status()["usingBuiltinDestination"] is True


def test_builtin_destination_is_used_without_a_credential(reporter_env):
    reporter, settings = reporter_env
    settings.update({"enableErrorReporting": True, "errorReportingFormat": FORMAT_SENTRY})
    assert reporter.dsn() == DEFAULT_SENTRY_DSN
    assert reporter.using_builtin_destination() is True
    assert reporter.configuration_problem() is None
    assert reporter.usable() is True
    assert reporter.destination_display() == "https://errors.loki.m4p.uk/1"


def test_a_user_credential_overrides_the_builtin_destination(reporter_env):
    reporter, settings = reporter_env
    settings.set_credential("sentry", DSN)
    assert reporter.dsn() == DSN
    assert reporter.using_builtin_destination() is False
    assert reporter.destination_display() == "https://glitchtip.example.com/42"


def test_the_builtin_destination_key_is_never_displayed(reporter_env):
    reporter, _settings = reporter_env
    assert reporter.using_builtin_destination() is True
    assert "01541d68" not in json.dumps(reporter.status())
    assert "01541d68" not in json.dumps(reporter.preview())


async def test_builtin_destination_receives_reports(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    settings.update({"enableErrorReporting": True, "errorReportingFormat": FORMAT_SENTRY})
    calls: list[str] = []
    monkeypatch.setattr(reporter, "_post_sync", lambda url, headers, body: (calls.append(url), 200)[1])

    result = await reporter.maybe_send(ErrorEvent.build(code="A", message="b").to_dict())
    assert result == {"sent": True, "status": 200}
    assert calls == ["https://errors.loki.m4p.uk/api/1/store/"]


async def test_disabled_reporter_sends_nothing(reporter_env, monkeypatch):
    reporter, _settings = reporter_env

    def explode(*_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("the reporter must not touch the network while disabled")

    monkeypatch.setattr(reporter, "_post_sync", explode)
    result = await reporter.maybe_send(ErrorEvent.build(code="A", message="b").to_dict())
    assert result == {"sent": False, "reason": "disabled"}


async def test_sentry_format_posts_to_the_store_api(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    enable_sentry(settings)
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url, headers, body):
        calls.append((url, headers, body))
        return 200

    monkeypatch.setattr(reporter, "_post_sync", fake_post)
    event = ErrorEvent.build(code="UPDATE_FAILED", message="boom", operation="update_addon").to_dict()
    result = await reporter.maybe_send(event)

    assert result == {"sent": True, "status": 200}
    url, headers, body = calls[0]
    assert url == "https://glitchtip.example.com/api/42/store/"
    assert "sentry_key=abc123def456" in headers["X-Sentry-Auth"]
    assert body["tags"]["code"] == "UPDATE_FAILED"
    assert reporter.status()["sent"] == 1
    assert reporter.status()["lastSentAt"] is not None


async def test_custom_format_posts_the_journal_event(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    settings.update(
        {
            "enableErrorReporting": True,
            "errorReportingFormat": FORMAT_CUSTOM,
            "errorReportingEndpoint": "https://collector.example.com/ingest",
        }
    )
    calls: list[dict] = []
    monkeypatch.setattr(reporter, "_post_sync", lambda url, headers, body: (calls.append(body), 202)[1])

    await reporter.maybe_send(ErrorEvent.build(code="UPDATE_FAILED", message="boom").to_dict())
    assert calls[0]["schema"] == 1
    assert calls[0]["plugin"]["name"] == "Azeroth Addons"
    assert calls[0]["event"]["code"] == "UPDATE_FAILED"


async def test_reporter_refuses_plain_http_endpoints(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    settings.update(
        {
            "enableErrorReporting": True,
            "errorReportingFormat": FORMAT_CUSTOM,
            "errorReportingEndpoint": "http://collector.example.com/ingest",
        }
    )
    monkeypatch.setattr(reporter, "_post_sync", lambda *a, **k: pytest.fail("must not send over http"))
    result = await reporter.maybe_send(ErrorEvent.build(code="A", message="b").to_dict())
    assert result["sent"] is False
    assert "Plain HTTP" in result["reason"]


async def test_same_error_is_not_reported_twice_in_an_hour(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    enable_sentry(settings)
    monkeypatch.setattr(reporter, "_post_sync", lambda url, headers, body: 200)

    event = ErrorEvent.build(code="UPDATE_FAILED", message="boom").to_dict()
    assert (await reporter.maybe_send(event))["sent"] is True
    second = await reporter.maybe_send(event)
    assert second["sent"] is False
    assert "already reported" in second["reason"]


async def test_hourly_cap_is_enforced(tmp_path: Path, monkeypatch):
    settings = make_settings(tmp_path)
    enable_sentry(settings)
    reporter = ErrorReporter(settings, max_per_hour=2)
    monkeypatch.setattr(reporter, "_post_sync", lambda url, headers, body: 200)

    for index in range(2):
        result = await reporter.maybe_send(ErrorEvent.build(code="C", message=f"failure {index}").to_dict())
        assert result["sent"] is True
    limited = await reporter.maybe_send(ErrorEvent.build(code="C", message="failure 3").to_dict())
    assert limited["sent"] is False
    assert "Rate limited" in limited["reason"]


async def test_failures_are_recorded_not_retried(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    enable_sentry(settings)

    def failing(url, headers, body):
        raise urllib.error.HTTPError(url, 500, "server error", {}, None)

    monkeypatch.setattr(reporter, "_post_sync", failing)
    result = await reporter.maybe_send(ErrorEvent.build(code="A", message="b").to_dict())
    assert result["sent"] is False
    status = reporter.status()
    assert status["failed"] == 1
    assert status["lastError"] == "HTTP 500"


async def test_send_test_works_before_reporting_is_enabled(reporter_env, monkeypatch):
    reporter, settings = reporter_env
    settings.update({"errorReportingFormat": FORMAT_SENTRY})
    settings.set_credential("sentry", DSN)
    calls: list[str] = []
    monkeypatch.setattr(reporter, "_post_sync", lambda url, headers, body: (calls.append(url), 200)[1])

    assert reporter.enabled() is False
    result = await reporter.send_test()
    assert result == {"sent": True, "status": 200}
    assert calls == ["https://glitchtip.example.com/api/42/store/"]


def test_preview_masks_the_dsn_key(reporter_env):
    reporter, settings = reporter_env
    settings.set_credential("sentry", DSN)
    preview = reporter.preview()
    assert preview["format"] == FORMAT_SENTRY
    assert "abc123def456" not in json.dumps(preview)
    assert "sentry_key=<redacted>" in preview["request"]["headers"]["X-Sentry-Auth"]
    assert preview["request"]["body"]["event_id"]
    assert preview["problem"] is None


def test_preview_reports_configuration_problems_for_a_custom_endpoint(reporter_env):
    """An endpoint that is still missing is the remaining misconfiguration."""
    reporter, settings = reporter_env
    settings.update({"errorReportingFormat": FORMAT_CUSTOM})
    preview = reporter.preview()
    assert preview["request"] is None
    assert preview["problem"]


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://collector.example.com/ingest", True),
        ("http://localhost:8080/ingest", True),
        ("http://collector.example.com/ingest", False),
        ("ftp://collector.example.com/ingest", False),
        ("", False),
    ],
)
def test_endpoint_validation(url, ok):
    assert (validate_endpoint(url) is None) is ok


def test_redaction_survives_a_full_round_trip(tmp_path: Path, monkeypatch):
    """Journal -> Sentry payload, with a hostile-looking error message."""
    home = tmp_path / "home" / "deck"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    settings = make_settings(tmp_path)
    journal = ErrorJournal(JsonStore(tmp_path / "settings"))

    recorded = journal.record(
        ErrorEvent.build(
            code="NETWORK_ERROR",
            message=f"Could not reach {home}/secrets",
            details="Authorization: Bearer super-secret-token",
            installation="retail-1a2b3c",
        )
    )
    payload = build_event(recorded)
    serialised = json.dumps(payload)
    assert str(home) not in serialised
    assert "super-secret-token" not in serialised
    assert "redacted" in serialised
    # The useful, non-sensitive facts survive.
    assert payload["tags"]["installation"] == "retail-1a2b3c"
    assert "Could not reach" in payload["message"]["formatted"]
