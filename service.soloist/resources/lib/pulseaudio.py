"""Route Soloist's audio into Kodi.

Soloist plays into a PulseAudio null sink; module-rtp-send streams that
sink's monitor to 127.0.0.1 over RTP, and Kodi plays the RTP stream like any
other audio file. Same approach as LibreELEC's Librespot add-on.
"""

import socket
import subprocess
import threading

import utils

_SAP_PORT = 9875


def _pactl(*args):
    result = subprocess.run(
        ["pactl", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", check=False,
    )
    output = result.stdout.strip()
    utils.debug(f"pactl {' '.join(args)}: {output}")
    return output if result.returncode == 0 else ""


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


class RtpSink:
    def __init__(self, sink, port, address="127.0.0.1"):
        self.sink = sink
        self.url = f"rtp://{address}:{port}"
        self._sap = _SapSink(address)
        self._modules = []
        _unload_stale(sink)
        null_sink = _pactl("load-module", "module-null-sink", f"sink_name={sink}")
        if null_sink:
            self._modules.append(null_sink)
        rtp = _pactl(
            "load-module",
            "module-rtp-send",
            f"source={sink}.monitor",
            f"destination_ip={address}",
            f"port={port}",
            "inhibit_auto_suspend=always",
        )
        if rtp:
            self._modules.append(rtp)
        if len(self._modules) != 2:
            self.close()
            raise RuntimeError("could not set up the PulseAudio sink")
        self.suspend(True)

    def suspend(self, suspended):
        _pactl("suspend-sink", self.sink, "1" if suspended else "0")

    def close(self):
        for module in reversed(self._modules):
            _pactl("unload-module", module)
        self._modules = []
        self._sap.close()
