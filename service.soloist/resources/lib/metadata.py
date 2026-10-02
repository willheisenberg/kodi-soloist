"""Turn Soloist WebSocket entities into what Kodi's music info tag needs.

No Kodi imports here, so the module is testable outside Kodi.
"""

_COVER_PREFERENCE = ("xlarge", "large", "default", "small")


def _name(entity):
    return ((entity or {}).get("decorations") or {}).get("identity", {}).get("name", "")


def cover_url(item):
    covers = (item.get("decorations") or {}).get("visual_identity", {}).get("cover") or []
    by_size = {cover.get("size"): cover.get("url") for cover in covers if cover.get("url")}
    for size in _COVER_PREFERENCE:
        if by_size.get(size):
            return by_size[size]
    return next(iter(by_size.values()), "")


def track_info(item):
    """Return title, artist, album, duration (seconds) and cover for an entity."""
    if not item:
        return {"title": "", "artist": "", "album": "", "duration": 0, "cover": ""}
    decorations = item.get("decorations") or {}
    creators = decorations.get("creators") or []
    artists = [_name(creator.get("entity")) for creator in creators]
    parent = (decorations.get("parent") or {}).get("entity")
    duration_ms = (decorations.get("playback") or {}).get("duration_ms") or 0
    return {
        "title": _name(item),
        "artist": ", ".join(artist for artist in artists if artist),
        "album": _name(parent),
        "duration": round(duration_ms / 1000),
        "cover": cover_url(item),
    }

