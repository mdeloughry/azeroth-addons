from __future__ import annotations

import ssl
from pathlib import Path

from azeroth_addons import networking
from azeroth_addons.providers import http
from azeroth_addons.telemetry.reporter import ErrorReporter


def test_embedded_python_loads_system_roots(monkeypatch):
    # Embedded OpenSSL can have an empty default trust store even though the
    # OS bundle exists. Reproduce this without changing machine configuration.
    empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    bundle = ssl.get_default_verify_paths().cafile
    assert bundle and Path(bundle).is_file()
    monkeypatch.setattr(networking.ssl, "create_default_context", lambda: empty)
    monkeypatch.setattr(networking, "SYSTEM_CA_BUNDLES", (bundle,))
    context = networking.create_ssl_context()
    assert context.cert_store_stats()["x509_ca"] > 0
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_missing_system_roots_never_disables_verification(monkeypatch):
    monkeypatch.setattr(networking, "SYSTEM_CA_BUNDLES", ("/missing/ca.pem",))
    context = networking.create_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_provider_and_reporter_use_shared_trust_context(monkeypatch):
    context = ssl.create_default_context()
    seen = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return b"{}"

    def open_request(request, *, timeout, context):
        seen.append(context)
        return Response()

    monkeypatch.setattr(http, "create_ssl_context", lambda: context)
    monkeypatch.setattr("azeroth_addons.telemetry.reporter.create_ssl_context", lambda: context)
    monkeypatch.setattr(http.urllib.request, "urlopen", open_request)
    http._perform("https://example.test", headers={}, timeout=1)
    reporter = object.__new__(ErrorReporter)
    reporter._timeout = 1
    reporter._post_sync("https://example.test", {}, {})
    assert seen == [context, context]
