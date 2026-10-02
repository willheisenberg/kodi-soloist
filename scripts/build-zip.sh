#!/bin/sh
# Package the add-on as an installable Kodi zip in dist/.
set -eu
cd "$(dirname "$0")/.."
version=$(sed -n 's/.*<addon id="service.soloist"[^>]* version="\([^"]*\)".*/\1/p' service.soloist/addon.xml)
mkdir -p dist
out="dist/service.soloist-${version}.zip"
rm -f "$out"
zip -qr "$out" service.soloist -x '*/__pycache__/*' '*.pyc'
echo "$out"
