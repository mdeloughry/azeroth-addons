#!/usr/bin/env bash
#
# Build a distributable Decky plugin zip:
#
#   azeroth-addons-<version>.zip
#     azeroth-addons/
#       bin/instawow           (pinned, checksum-verified)
#       dist/index.js          (built frontend)
#       backend/               (stdlib-only Python backend)
#       third_party/instawow/COPYING
#       main.py plugin.json package.json py_modules/
#       README.md LICENSE THIRD_PARTY_LICENSES.md
#
# Copy the extracted folder into /home/deck/homebrew/plugins and restart Decky.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="azeroth-addons"
OUT="${ROOT}/release"
STAGE="${OUT}/${NAME}"

VERSION="$(python3 - "${ROOT}/package.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    print(json.load(handle).get("version", "0.0.0"))
PY
)"

echo "Packaging ${NAME} ${VERSION}"

echo "1/4  Building the frontend…"
if [ ! -d "${ROOT}/node_modules" ]; then
  (cd "${ROOT}" && pnpm install)
fi
(cd "${ROOT}" && pnpm run build)

echo "2/4  Ensuring the bundled engine…"
"${ROOT}/scripts/fetch-instawow.sh"

echo "3/4  Staging files…"
rm -rf "${STAGE}"
mkdir -p "${STAGE}/py_modules"
cp -R "${ROOT}/dist" "${STAGE}/dist"
cp -R "${ROOT}/bin" "${STAGE}/bin"
cp -R "${ROOT}/backend" "${STAGE}/backend"
if [ -d "${ROOT}/third_party" ]; then
  cp -R "${ROOT}/third_party" "${STAGE}/third_party"
fi
cp "${ROOT}/main.py" "${ROOT}/plugin.json" "${ROOT}/package.json" "${STAGE}/"
cp "${ROOT}/README.md" "${ROOT}/LICENSE" "${ROOT}/THIRD_PARTY_LICENSES.md" "${STAGE}/"
if [ -f "${ROOT}/py_modules/.keep" ]; then
  cp "${ROOT}/py_modules/.keep" "${STAGE}/py_modules/.keep"
fi

# Build artefacts and secrets must never ship.
find "${STAGE}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${STAGE}" -name '*.pyc' -delete
# Source maps are not needed in the distributed build: the source is public.
find "${STAGE}/dist" -name '*.map' -delete
rm -f "${STAGE}/bin/.instawow-"*".sha256"

echo "4/4  Creating the archive…"
ARCHIVE="${OUT}/${NAME}-${VERSION}.zip"
rm -f "${ARCHIVE}"
(cd "${OUT}" && zip -r -q "$(basename "${ARCHIVE}")" "${NAME}")

echo
echo "Built ${ARCHIVE}"
unzip -l "${ARCHIVE}" | tail -n 20
