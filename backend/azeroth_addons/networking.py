"""Verified HTTPS for Decky's embedded Python and the host's CA store."""

from __future__ import annotations

import ssl
from pathlib import Path

# OpenSSL in an embedded Python build may look in a build-machine prefix.
# SteamOS/Arch and Debian expose their maintained trust stores at these paths.
SYSTEM_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
)


def create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    for bundle in SYSTEM_CA_BUNDLES:
        if not Path(bundle).is_file():
            continue
        try:
            context.load_verify_locations(cafile=bundle)
        except (OSError, ssl.SSLError):
            continue
        break
    return context
