"""Mirror Soloist's playback in Kodi and hand Kodi's controls back to it.

Soloist is the source of truth. Its WebSocket events drive the Kodi player
(play/pause/stop of the RTP stream, now-playing info); Kodi's pause, resume
and stop are sent back as Soloist commands. Commands are only sent when they
change Soloist's state, so the echo of our own Kodi actions is harmless.
"""

import json
import threading
import time

import metadata
import utils
import xbmc
import xbmcgui

_ACTIVE = ("playing", "buffering")


class Player(xbmc.Player):
    def __init__(self, url, send_command):
        super().__init__()
        self._url = url
        self._send = send_command
        self._lock = threading.RLock()
        self._status = "idle"
        self._ours = False
        self._starting = False
        # A client asked for the device to be released and handles Kodi itself.
        self._released = False
        # Kodi's pause/resume callbacks within this window echo our own call.
        self._own_action_until = 0.0
        # Set on shutdown. Player calls block on Kodi's main thread, which is
        # itself waiting for the add-on to stop then: no more calls after it.
        self._closing = threading.Event()
        self._item = xbmcgui.ListItem(path=url)
        self._item.setProperties({"inputstream": "inputstream.ffmpeg"})
        self._tag = self._item.getMusicInfoTag()

    # --- state helpers --------------------------------------------------

    def _playing_ours(self):
        try:
            return self.isPlaying() and self.getPlayingFile() == self._url
        except RuntimeError:
            return False

    def _playing_other(self):
        return self.isPlaying() and not self._playing_ours()

    @staticmethod
    def _kodi_paused():
        return xbmc.getCondVisibility("Player.Paused")

    def _set_kodi_paused(self, paused):
        """Pause or resume Kodi explicitly.

        xbmc.Player.pause() toggles, and Player.Paused lags behind it: Soloist
        reports one pause twice (playback_changed + playback_state), so two
        toggles undid each other and the resume echoed back as "play".
        """
        self._own_action_until = time.monotonic() + 1.0
        players = json.loads(xbmc.executeJSONRPC(json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "Player.GetActivePlayers"}
        ))).get("result") or []
        for active in players:
            if active.get("type") == "audio":
                xbmc.executeJSONRPC(json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "Player.PlayPause",
                    "params": {"playerid": active["playerid"], "play": not paused},
                }))

    # --- Soloist -> Kodi ------------------------------------------------

    def on_status(self, status):
        if self._closing.is_set():
            return
        with self._lock:
            self._status = status
            if status in _ACTIVE:
                self._released = False
                if self._playing_ours():
                    if self._kodi_paused():
                        self._set_kodi_paused(False)
                elif self._playing_other() and utils.get_bool("dnd_kodi"):
                    utils.log("Kodi is busy, pausing Soloist")
                    self._send("pause")
                elif not self._starting:
                    # play() returns before onAVStarted; don't start twice.
                    self._starting = True
                    # Tell JSON-RPC clients (the PartyQueue bot) before Kodi
                    # reports the outgoing item stopped, so they park their
                    # queue instead of restarting it.
                    xbmc.executebuiltin(f"NotifyAll({utils.ADDON_ID},soloist_takeover)", True)
                    self.play(self._url, self._item)
            elif self._released:
                # The client stops or replaces the stream itself. Checking
                # for our stream and stopping it is not atomic: the stop could
                # hit what the client has started in the meantime.
                pass
            elif status == "paused":
                if self._playing_ours():
                    self._set_kodi_paused(True)
            elif status == "idle" and self._playing_ours():
                self.stop()

    def on_track(self, item):
        if self._closing.is_set():
            return
        info = metadata.track_info(item)
        with self._lock:
            self._tag.setTitle(info["title"])
            self._tag.setArtist(info["artist"])
            self._tag.setAlbum(info["album"])
            self._tag.setDuration(info["duration"])
            self._item.setArt({"thumb": info["cover"], "fanart": info["cover"]})
            if self._playing_ours():
                self.updateInfoTag(self._item)
            elif info["title"] and not self.isPlaying():
                utils.notification(info["artist"] or info["album"], info["title"])

    def on_inactive(self):
        self.on_status("idle")

    def on_release(self):
        """A client gives the device back and takes care of Kodi's player."""
        with self._lock:
            self._released = True

    # --- Kodi -> Soloist ------------------------------------------------

    def onAVStarted(self):
        utils.debug("kodi: onAVStarted")
        with self._lock:
            self._starting = False
            if self._playing_ours():
                self._ours = True
                self.updateInfoTag(self._item)
            else:
                # Something else took over Kodi (e.g. a video).
                if self._ours or self._status in _ACTIVE:
                    self._send("pause")
                self._ours = False

    def _own_echo(self):
        return time.monotonic() < self._own_action_until

    def onPlayBackPaused(self):
        utils.debug("kodi: onPlayBackPaused")
        with self._lock:
            if self._own_echo():
                return
            if self._ours and self._status in _ACTIVE:
                self._send("pause")

    def onPlayBackResumed(self):
        utils.debug("kodi: onPlayBackResumed")
        with self._lock:
            if self._own_echo():
                return
            if self._ours and self._status == "paused":
                self._send("play")

    def _on_ended(self):
        with self._lock:
            self._starting = False
            if self._ours and self._status in _ACTIVE:
                self._send("pause")
            self._ours = False

    def onPlayBackStopped(self):
        utils.debug("kodi: onPlayBackStopped")
        self._on_ended()

    def onPlayBackEnded(self):
        utils.debug("kodi: onPlayBackEnded")
        self._on_ended()

    def onPlayBackError(self):
        self._on_ended()

    def shutdown(self):
        # No lock and no blocking Player call: another thread may hold the
        # lock inside a Kodi call that waits for this shutdown to finish.
        self._closing.set()
        if self._playing_ours():
            xbmc.executebuiltin("PlayerControl(Stop)")
