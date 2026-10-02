#!/bin/sh
# Starts Spotify Soloist inside the container.
#
# Secrets arrive on stdin so they never show up in `docker inspect`, the
# compose file or the image:
#   line 1: Soloist API key
#   line 2: base64 PulseAudio cookie (may be empty)
#
# Configuration comes from the environment:
#   SOLOIST_NAME, SOLOIST_VOLUME, SOLOIST_CACHE_MB, SOLOIST_WS
set -eu

log() { echo "entrypoint: $*" >&2; }

IFS= read -r API_KEY || true
IFS= read -r COOKIE_B64 || true
if [ -z "${API_KEY:-}" ]; then
    log "no API key on stdin"
    exit 1
fi

if [ -n "${COOKIE_B64:-}" ]; then
    printf '%s' "$COOKIE_B64" | base64 -d > /tmp/pulse-cookie
    export PULSE_COOKIE=/tmp/pulse-cookie
fi
unset COOKIE_B64

case "$(uname -m)" in
    aarch64) ARCH=arm64 ;;
    armv7l|armv8l) ARCH=arm32 ;;
    x86_64) ARCH=x86_64 ;;
    *) log "unsupported architecture $(uname -m)"; exit 1 ;;
esac
URL="https://soloist-builds.spotifycdn.com/soloist_release_${ARCH}.tar.gz"

# Fetch the current build on every start: builds expire after 90 days
# (exit code 10), so a restart is all an update needs. Keep the old binary
# when the download fails.
mkdir -p /data/bin /data/state /data/cache
rm -rf /data/new && mkdir /data/new
if curl -fsSL --retry 2 --max-time 180 "$URL" | tar -xzf - -C /data/new soloist; then
    if ! cmp -s /data/new/soloist /data/bin/soloist; then
        mv /data/new/soloist /data/bin/soloist
        log "installed new Soloist build"
    fi
else
    log "download failed, keeping the installed build"
fi
rm -rf /data/new
if [ ! -x /data/bin/soloist ]; then
    log "no Soloist binary available"
    exit 1
fi
/data/bin/soloist --version >&2

exec /data/bin/soloist \
    --device-name "${SOLOIST_NAME:-Kodi}" \
    --api-key "$API_KEY" \
    --data-dir /data/state \
    --cache-dir /data/cache \
    --cache-size "${SOLOIST_CACHE_MB:-500}" \
    --initial-volume "${SOLOIST_VOLUME:-80}" \
    --ws "${SOLOIST_WS:-127.0.0.1:24879}"
