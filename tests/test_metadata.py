import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))

import metadata

# Shape taken from the Soloist WebSocket API reference ("Entity Shape").
TRACK = {
    "uri": "spotify:track:2JRo0gjbX4GrCqBYdRohoo",
    "entity_type": "track",
    "decorations": {
        "identity": {"name": "My Song"},
        "visual_identity": {
            "cover": [
                {"url": "https://i.scdn.co/image/small", "size": "small"},
                {"url": "https://i.scdn.co/image/large", "size": "large"},
            ]
        },
        "parent": {
            "entity": {
                "uri": "spotify:album:4aawyAB9vmqN3uQ7FjRGTy",
                "entity_type": "album",
                "decorations": {"identity": {"name": "Album Name"}},
            }
        },
        "creators": [
            {"entity": {"entity_type": "artist", "decorations": {"identity": {"name": "Artist A"}}}},
            {"entity": {"entity_type": "artist", "decorations": {"identity": {"name": "Artist B"}}}},
        ],
        "playback": {"duration_ms": 210400, "content_ratings": []},
    },
}


def test_track_info_full_entity():
    assert metadata.track_info(TRACK) == {
        "title": "My Song",
        "artist": "Artist A, Artist B",
        "album": "Album Name",
        "duration": 210,
        "cover": "https://i.scdn.co/image/large",
    }


def test_track_info_sparse_entity():
    # The playback_state example carries only identity and playback.
    item = {
        "uri": "spotify:track:x",
        "entity_type": "track",
        "decorations": {"identity": {"name": "My Song"}, "playback": {"duration_ms": 1000}},
    }
    info = metadata.track_info(item)
    assert info["title"] == "My Song"
    assert info["artist"] == info["album"] == info["cover"] == ""
    assert info["duration"] == 1


def test_track_info_empty():
    assert metadata.track_info(None)["title"] == ""
    assert metadata.track_info({"uri": "spotify:track:x"})["title"] == ""


def test_cover_falls_back_to_any_size():
    item = {"decorations": {"visual_identity": {"cover": [{"url": "u", "size": "odd"}]}}}
    assert metadata.cover_url(item) == "u"

