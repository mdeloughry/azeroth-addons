"""Azeroth Addons backend package.

Provider-neutral, engine-neutral addon management for World of Warcraft
installations, exposed to the Decky frontend over the plugin RPC channel.
"""

__version__ = "0.1.8"

# The bundled addon engine this build is pinned against. The release process
# downloads exactly this artifact and verifies it against the digest below
# before packaging (see scripts/fetch-instawow.sh).
BUNDLED_INSTAWOW_VERSION = "7.2.1"
BUNDLED_INSTAWOW_TARGET = "x86_64-unknown-linux-gnu"
BUNDLED_INSTAWOW_ARTIFACT = f"instawow-cli-{BUNDLED_INSTAWOW_VERSION}-{BUNDLED_INSTAWOW_TARGET}.zip"
BUNDLED_INSTAWOW_SHA256 = "4f211cb1055a4b1b2348af1be4820701de727cfad5f8f2cc7d527536a268766c"
BUNDLED_INSTAWOW_URL = (
    f"https://github.com/layday/instawow/releases/download/"
    f"v{BUNDLED_INSTAWOW_VERSION}/{BUNDLED_INSTAWOW_ARTIFACT}"
)
