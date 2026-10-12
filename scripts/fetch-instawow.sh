#!/usr/bin/env bash
#
# Fetch the pinned instawow release artifact, verify its checksum, and install
# it as bin/instawow.
#
# Pinning rules (see docs/implementation-plan.md):
#   * the version, target, artifact name and sha256 are literal constants here;
#   * a checksum mismatch is fatal - nothing is installed;
#   * the upstream LICENSE (GPL-3.0) ships alongside the binary.
#
# Instawow is GPL-3.0-or-later. Azeroth Addons bundles the unmodified official
# binary; see THIRD_PARTY_LICENSES.md.
set -euo pipefail

VERSION="7.2.1"
TARGET="x86_64-unknown-linux-gnu"
ARTIFACT="instawow-cli-${VERSION}-${TARGET}.zip"
SHA256="4f211cb1055a4b1b2348af1be4820701de727cfad5f8f2cc7d527536a268766c"
URL="https://github.com/layday/instawow/releases/download/v${VERSION}/${ARTIFACT}"
COPYING_URL="https://raw.githubusercontent.com/layday/instawow/v${VERSION}/COPYING"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${ROOT}/bin"
THIRD_PARTY_DIR="${ROOT}/third_party/instawow"
STAMP="${BIN_DIR}/.instawow-${VERSION}.sha256"

if [ -x "${BIN_DIR}/instawow" ] && [ -f "${STAMP}" ] && [ -s "${THIRD_PARTY_DIR}/COPYING" ]; then
  echo "instawow ${VERSION} already installed; nothing to do."
  exit 0
fi

mkdir -p "${BIN_DIR}" "${THIRD_PARTY_DIR}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "Downloading instawow ${VERSION} (${TARGET})…"
curl -fsSL --retry 3 --retry-delay 2 -o "${TMP}/${ARTIFACT}" "${URL}"

echo "Verifying sha256…"
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum "${TMP}/${ARTIFACT}" | awk '{print $1}')"
else
  ACTUAL="$(shasum -a 256 "${TMP}/${ARTIFACT}" | awk '{print $1}')"
fi

if [ "${ACTUAL}" != "${SHA256}" ]; then
  echo "Checksum mismatch - refusing to install." >&2
  echo "  expected ${SHA256}" >&2
  echo "  actual   ${ACTUAL}" >&2
  exit 1
fi

echo "Extracting…"
unzip -o -q "${TMP}/${ARTIFACT}" -d "${TMP}/out"
BIN="$(find "${TMP}/out" -maxdepth 2 -type f -name 'instawow*' ! -name '*.zip' | head -n 1)"
if [ -z "${BIN}" ]; then
  echo "The archive did not contain an instawow binary." >&2
  exit 1
fi

echo "Fetching upstream licence text…"
curl -fsSL --retry 3 --retry-delay 2 "${COPYING_URL}" -o "${TMP}/COPYING"
test -s "${TMP}/COPYING"
install -m 0755 "${BIN}" "${BIN_DIR}/instawow"
install -m 0644 "${TMP}/COPYING" "${THIRD_PARTY_DIR}/COPYING"
printf '%s\n' "${SHA256}" > "${STAMP}"

echo
echo "instawow ${VERSION} installed at bin/instawow"
echo "Note: the first run downloads the engine's embedded Python runtime."
"${BIN_DIR}/instawow" --version 2>/dev/null || echo "(cannot execute here - expected off-target)"
