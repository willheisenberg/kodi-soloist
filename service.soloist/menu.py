"""Program add-on entry: status of Soloist plus a few actions.

Talks to Soloist's WebSocket directly; the service keeps running untouched.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))

import metadata
import utils
import wsclient
import xbmcaddon
import xbmcgui

_TIMEOUT = 2.0


def _connect():
    try:
        ws = wsclient.WebSocket("127.0.0.1", int(utils.get_setting("ws_port")), timeout=_TIMEOUT)
    except OSError:
        return None
    ws.settimeout(_TIMEOUT)
    return ws


def _read_state(ws):
    """Soloist sends auth_state (and playback_state when logged in) on connect."""
    auth, playback = None, None
    try:
        while auth is None or (auth.get("logged_in") and playback is None):
            message = json.loads(ws.recv_text())
            if message.get("type") == "auth_state":
                auth = message
            elif message.get("type") == "playback_state":
                playback = message
    except (OSError, ValueError, wsclient.ConnectionClosed):
        pass
    return auth, playback


def _status_line(auth, playback):
    if auth is None:
        return utils.string(30300)
    if not auth.get("logged_in"):
        return utils.string(30301)
    if not auth.get("is_active"):
        return utils.string(30302)
    info = metadata.track_info((playback or {}).get("item"))
    track = " – ".join(part for part in (info["title"], info["artist"]) if part)
    status = (playback or {}).get("status")
    if track and status in ("playing", "buffering"):
        return utils.string(30303).format(track)
    if track and status == "paused":
        return utils.string(30304).format(track)
    return utils.string(30305)


def main():
    ws = _connect()
    auth, playback = _read_state(ws) if ws else (None, None)
    actions = []
    if auth and auth.get("is_active"):
        actions.append(("release", utils.string(30310)))
    actions.append(("settings", utils.string(30311)))

    choice = xbmcgui.Dialog().select(_status_line(auth, playback), [label for _, label in actions])
    action = actions[choice][0] if choice >= 0 else None
    if action == "release" and ws:
        try:
            ws.send_text(json.dumps({"type": "command", "command": "deactivate"}))
            utils.notification(utils.string(30312))
        except OSError as e:
            utils.log(f"release from menu failed: {e}")
    if ws:
        ws.close()
    if action == "settings":
        xbmcaddon.Addon().openSettings()


main()
