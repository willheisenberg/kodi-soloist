"""Route Soloist's audio into Kodi.

Soloist plays into a PulseAudio null sink; module-rtp-send streams that
sink's monitor to 127.0.0.1 over RTP, and Kodi plays the RTP stream through
an SDP file describing it. Similar to LibreELEC's Librespot add-on, which
streams 44.1 kHz and needs no SDP file.
"""

import json
import socket
import subprocess
import threading

import utils
import xbmc

_SAP_PORT = 9875
# 48 kHz, not 44.1 kHz: after the AV receiver is switched on, 44.1 kHz over
# HDMI can play too high and crackle until something opens it with 48 kHz.
_RATE = 48000
_CHANNELS = 2
_PAYLOAD_TYPE = 127


def _pactl(*args, quiet=False):
    result = subprocess.run(
        ["pactl", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", check=False,
    )
    output = result.stdout.strip()
    if not quiet:
        utils.debug(f"pactl {' '.join(args)}: {output}")
    return output if result.returncode == 0 else ""


def _pactl_list(kind):
    """`pactl list <kind>` as parsed JSON; empty if pactl fails."""
    try:
        return json.loads(_pactl("-f", "json", "list", kind, quiet=True) or "[]")
    except ValueError:
        return []


def _unload_stale(sink):
    """Unload modules a crashed or killed earlier run left behind."""
    for line in _pactl("list", "short", "modules").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        index, name, arguments = parts[0], parts[1], parts[2]
        if (name == "module-null-sink" and f"sink_name={sink}" in arguments.split()) or (
            name == "module-rtp-send" and f"source={sink}.monitor" in arguments.split()
        ):
            _pactl("unload-module", index)


class _SapSink:
    """Swallow module-rtp-send's SAP announcements.

    They go to 127.0.0.1:9875 as well; without a listener every packet earns
    an ICMP port-unreachable. The Librespot add-on runs `nc -lu` for this.
    """

    def __init__(self, address):
        self._stop = threading.Event()
        self._thread = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._sock.bind((address, _SAP_PORT))
        except OSError as e:
            utils.log(f"SAP port {_SAP_PORT} busy, not listening: {e}")
            self._sock.close()
            self._sock = None
            return
        # Kodi waits for every add-on thread on shutdown, and close() does not
        # wake a blocked recv(); poll so the thread notices _stop.
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        while not self._stop.is_set():
            try:
                self._sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sock:
            self._sock.close()


def sdp(address, port):
    """Describe the RTP stream for Kodi.

    Only 44.1 kHz has a static RTP payload type that Kodi plays without a
    description; module-rtp-send marks every other format as type 127.
    """
    return (
        "v=0\r\n"
        f"o=- 0 0 IN IP4 {address}\r\n"
        "s=Soloist\r\n"
        f"c=IN IP4 {address}\r\n"
        "t=0 0\r\n"
        f"m=audio {port} RTP/AVP {_PAYLOAD_TYPE}\r\n"
        f"a=rtpmap:{_PAYLOAD_TYPE} L16/{_RATE}/{_CHANNELS}\r\n"
    )


class RtpSink:
    def __init__(self, sink, port, sdp_path, address="127.0.0.1"):
        self.sink = sink
        # Kodi plays the stream through this description file.
        self.url = sdp_path
        with open(sdp_path, "w", encoding="utf-8") as f:
            f.write(sdp(address, port))
        self._sap = _SapSink(address)
        self._modules = []
        _unload_stale(sink)
        null_sink = _pactl(
            "load-module", "module-null-sink", f"sink_name={sink}",
            f"rate={_RATE}", f"channels={_CHANNELS}",
        )
        if null_sink:
            self._modules.append(null_sink)
        rtp = _pactl(
            "load-module",
            "module-rtp-send",
            f"source={sink}.monitor",
            f"destination_ip={address}",
            f"port={port}",
            "format=s16be",
            f"rate={_RATE}",
            f"channels={_CHANNELS}",
            "inhibit_auto_suspend=always",
        )
        if rtp:
            self._modules.append(rtp)
        if len(self._modules) != 2:
            self.close()
            raise RuntimeError("could not set up the PulseAudio sink")
        self.suspend(True)

    def ensure_routed(self):
        """Move our streams back if PulseAudio moved them elsewhere.

        module-switch-on-connect makes every new sink or source the default,
        and PulseAudio moves streams to the default when their device goes
        away. A sink loaded by another program once left the RTP stream on
        that sink's monitor: Kodi got no packets and stopped playback.
        """
        rtp_module = self._modules[-1]
        monitor = f"{self.sink}.monitor"
        sources = {s["index"]: s["name"] for s in _pactl_list("sources")}
        for output in _pactl_list("source-outputs"):
            source = sources.get(output["source"], output["source"])
            if output.get("owner_module") == rtp_module and source != monitor:
                utils.log(f"RTP stream was moved to {source}, moving it back", xbmc.LOGWARNING)
                _pactl("move-source-output", str(output["index"]), monitor)
        sinks = {s["index"]: s["name"] for s in _pactl_list("sinks")}
        for stream in _pactl_list("sink-inputs"):
            sink = sinks.get(stream["sink"], stream["sink"])
            ours = stream.get("properties", {}).get("application.process.binary") == "soloist"
            if ours and sink != self.sink:
                utils.log(f"Spotify stream was moved to {sink}, moving it back", xbmc.LOGWARNING)
                _pactl("move-sink-input", str(stream["index"]), self.sink)

    def suspend(self, suspended):
        _pactl("suspend-sink", self.sink, "1" if suspended else "0")

    def close(self):
        for module in reversed(self._modules):
            _pactl("unload-module", module)
        self._modules = []
        self._sap.close()
