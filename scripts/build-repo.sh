#!/bin/sh
# Build the Kodi repository in repo/: add-on zips, addons.xml and its checksum.
# A zip is only built if its version is not there yet, so bump the version first.
set -eu
cd "$(dirname "$0")/.."
mkdir -p repo
{
    echo '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    echo '<addons>'
    for addon in repository.soloist service.soloist; do
        version=$(sed -n "s/.*<addon id=\"$addon\"[^>]* version=\"\([^\"]*\)\".*/\1/p" "$addon/addon.xml")
        zip="repo/$addon/$addon-$version.zip"
        if [ ! -f "$zip" ]; then
            rm -rf "repo/$addon"
            mkdir -p "repo/$addon"
            zip -qr "$zip" "$addon" -x '*/__pycache__/*' '*.pyc'
            # Kodi loads the artwork shown in the add-on browser from next to the zip.
            for asset in $(sed -n 's/.*<\(icon\|fanart\)>\(.*\)<\/.*/\2/p' "$addon/addon.xml"); do
                mkdir -p "repo/$addon/$(dirname "$asset")"
                cp "$addon/$asset" "repo/$addon/$asset"
            done
        fi
        sed '/<?xml/d' "$addon/addon.xml"
    done
    echo '</addons>'
} > repo/addons.xml
md5sum < repo/addons.xml | cut -d' ' -f1 > repo/addons.xml.md5
find repo -type f | sort
