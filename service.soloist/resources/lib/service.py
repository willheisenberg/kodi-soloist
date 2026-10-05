import json
import threading

import container
import device
import player
import pulseaudio
import utils
import wsclient
import xbmc

_MAX_FAILURES = 5
# JSONRPC.NotifyAll from the PartyQueue bot when it stops playback.
_RELEASE_NOTIFICATION = "Other.soloist_release"


class _NotConfigured(Exception):
    pass


class Session:
    """Sink, container, WebSocket and Kodi player for one configuration."""

    def __init__(self, monitor):
        if not container.read_api_key():
            utils.notification(utils.string(30201), time=10000)
            raise _NotConfigured(f"no API key in {container.KEY_FILE}")
        container.ensure_image()
        self._monitor = monitor
        self._closed = threading.Event()
        self._ws = None
        self._device = device.Device()
        self._failures = 0
        self._ws_port = int(utils.get_setting("ws_port"))
        self._sink = pulseaudio.RtpSink("soloist", int(utils.get_setting("rtp_port")))
        try:
            self._player = player.Player(self._sink.url, self.send)
            self._container = container.Container(self._on_container_exit)
        except Exception:
            self._sink.close()
            raise
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    # --- container ------------------------------------------------------

    def _on_container_exit(self, returncode):
        if self._closed.is_set():
            return
        if returncode == container.EXIT_EXPIRED:
            utils.notification(utils.string(30202))
        self._failures += 1
        if self._failures > _MAX_FAILURES:
            utils.notification(utils.string(30203), time=10000)
            return
        if self._closed.wait(min(60, 5 * self._failures)):
            return
        utils.log(f"restarting container (attempt {self._failures})")
        self._container = container.Container(self._on_container_exit)

    # --- WebSocket ------------------------------------------------------

    def send(self, command, **fields):
        ws = self._ws
        if ws is None:
            return
        utils.debug(f"-> {command} {fields or ''}")
        try:
            ws.send_text(json.dumps({"type": "command", "command": command, **fields}))
        except OSError as e:
            utils.log(f"sending {command} failed: {e}")

    def _ws_loop(self):
        while not self._closed.is_set():
            try:
                ws = wsclient.WebSocket("127.0.0.1", self._ws_port)
            except OSError:
                self._closed.wait(1)
                continue
            utils.log("connected to Soloist")
            self._ws = ws
            self.send("get_auth_state")
            try:
                while True:
                    self._dispatch(json.loads(ws.recv_text()))
            except (wsclient.ConnectionClosed, OSError, ValueError) as e:
                utils.log(f"WebSocket ended: {e}")
            finally:
                self._ws = None
                ws.close()
                self._player.on_inactive()
                self._sink.suspend(True)
            self._closed.wait(1)

    def _pin_volume(self, volume):
        """Undo volume changes from the app if the volume is pinned.

        Soloist scales the audio itself; Kodi's own volume stays untouched.
        With the setting on, the receiver is the only volume control.
        """
        if volume is None or volume == 100 or not utils.get_bool("pin_volume"):
            return
        utils.log(f"app set volume {volume}, pinning it to 100")
        self.send("set_volume", volume=100)

    def _on_status(self, status):
        self._sink.suspend(status == "idle")
        self._player.on_status(status)

    def _dispatch(self, message):
        kind = message.get("type")
        if kind not in ("position_sync", "queue_changed", "track_changed"):
            utils.debug(f"<- {kind} {message.get('status') or message.get('is_active') or ''}")
        # Another device playing on the account is no playback of ours.
        status = self._device.update(message)
        if kind == "auth_state":
            if message.get("logged_in"):
                self._failures = 0
                self.send("get_state")
            else:
                self._player.on_inactive()
        elif kind == "playback_state":
            self._player.on_track(message.get("item"))
            self._on_status(status)
            self._pin_volume(message.get("volume"))
        elif kind == "track_changed":
            self._player.on_track(message.get("item"))
        elif kind == "playback_changed":
            self._on_status(status)
        elif kind == "volume_changed":
            self._pin_volume(message.get("volume"))
        elif kind == "device_changed":
            self._on_status(status)
        elif kind == "error":
            utils.log(f"Soloist error: {message.get('message')}", xbmc.LOGWARNING)

    def release(self):
        """Give up the Spotify Connect device; the app moves back to the phone."""
        utils.log("release requested")
        self._player.on_release()
        self.send("deactivate")

    def close(self):
        self._closed.set()
        self._player.shutdown()
        self._container.stop()
        ws = self._ws
        if ws:
            ws.close()
        # Kodi waits for every add-on thread before it unloads the add-on.
        self._ws_thread.join(timeout=2)
        self._sink.close()


class Monitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self._settings_changed = threading.Event()
        self._session = None

    def onSettingsChanged(self):
        self._settings_changed.set()

    def onNotification(self, sender, method, data):
        session = self._session
        if method == _RELEASE_NOTIFICATION and session:
            session.release()

    def run(self):
        while not self.abortRequested():
            self._settings_changed.clear()
            session = None
            try:
                session = Session(self)
                self._session = session
            except _NotConfigured as e:
                utils.log(str(e))
            except Exception as e:  # noqa: BLE001 - keep the service alive, retry on settings change
                utils.log(f"start failed: {e}", xbmc.LOGERROR)
                utils.notification(utils.string(30204), time=10000)
            while not self._settings_changed.is_set():
                if self.waitForAbort(1):
                    break
            self._session = None
            if session:
                session.close()


def run():
    Monitor().run()
