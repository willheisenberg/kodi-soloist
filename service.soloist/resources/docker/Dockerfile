# Runtime for Spotify Soloist. The Soloist binary itself is not part of the
# image (Spotify forbids redistributing it); entrypoint.sh downloads it from
# Spotify's CDN into the /data volume on every start.
FROM debian:trixie-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libatomic1 libpulse0 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --user-group --no-create-home --home-dir /tmp soloist \
 && mkdir -p /data \
 && chown soloist:soloist /data

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENV HOME=/tmp
USER soloist
VOLUME /data
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
