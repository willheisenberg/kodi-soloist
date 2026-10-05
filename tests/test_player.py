import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))

URL = "rtp://127.0.0.1:23433"


class _Tag:
    def __getattr__(self, name):
        return lambda *args: None


class _ListItem:
    def __init__(self, path=""):
        pass

    def setProperties(self, properties):
        pass

    def setArt(self, art):
        pass

    def getMusicInfoTag(self):
        return _Tag()


class _KodiPlayer:
    """Stands in for xbmc.Player: `playing` is the file Kodi plays, or None."""

    playing = None

    def __init__(self):
        self.stopped = 0
        self.started = []

    def isPlaying(self):
        return self.playing is not None

    def getPlayingFile(self):
        return self.playing

    def play(self, url, item):
        self.started.append(url)

    def stop(self):
        self.stopped += 1


class _Addon:
    def getAddonInfo(self, key):
        return "service.soloist"

    def getSetting(self, key):
        return ""


def _module(name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    sys.modules[name] = module


# Kodi's Python API only exists inside Kodi.
_module(
    "xbmc", Player=_KodiPlayer, LOGINFO=1, LOGDEBUG=0,
    log=lambda message, level=1: None,
    executebuiltin=lambda command, wait=False: None,
    executeJSONRPC=lambda request: '{"result": []}',
    getCondVisibility=lambda condition: False,
)
_module("xbmcgui", ListItem=_ListItem)
_module("xbmcaddon", Addon=_Addon)

import player


def _player(playing):
    p = player.Player(URL, lambda command, **fields: None)
    p.playing = playing
    return p


def test_idle_stops_our_stream():
    p = _player(URL)

    p.on_status("idle")

    assert p.stopped == 1


def test_idle_after_a_release_leaves_kodi_to_the_client():
    p = _player(URL)

    p.on_release()
    p.on_status("paused")
    p.on_status("idle")

    assert p.stopped == 0


def test_playback_after_a_release_is_mirrored_again():
    p = _player(None)
    p.on_release()
    p.on_status("idle")

    p.on_status("playing")
    p.playing = URL
    p.on_status("idle")

    assert p.started == [URL]
    assert p.stopped == 1
