"""Run Spotify Soloist in an isolated Docker container.

Soloist is a closed-source binary, so it gets no access to the host beyond
the PulseAudio socket and the network (Spotify Connect discovery needs host
networking). It runs as an unprivileged user with a read-only root
filesystem and no capabilities. Secrets go in over stdin, never as docker
arguments or mounted files.
"""

import base64
import os
import subprocess
import threading

import utils

DOCKER = "/storage/.kodi/addons/service.system.docker/bin/docker"
CONTAINER = "soloist"
IMAGE = f"kodi-soloist:{utils.ADDON_VERSION}"
VOLUME = "soloist-data"
KEY_FILE = "/storage/.config/soloist/api_key"
PULSE_SOCKET = "/var/run/pulse/native"
PULSE_COOKIE = "/var/run/pulse/.config/pulse/cookie"
EXIT_EXPIRED = 10


def _docker(*args, **kwargs):
    return subprocess.run(
        [DOCKER, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def initial_volume():
    # Volume stays with the AV receiver unless the app may control it.
    return utils.get_setting("initial_volume") if utils.get_bool("spotify_volume") else "100"


def read_api_key():
    try:
        with open(KEY_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def _read_cookie():
    try:
        with open(PULSE_COOKIE, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def ensure_image():
    if _docker("image", "inspect", IMAGE).returncode == 0:
        return
    utils.notification(utils.string(30200))
    context = os.path.join(utils.ADDON_PATH, "resources", "docker")
    result = _docker("build", "--pull", "-t", IMAGE, context)
    utils.log(result.stdout)
    if result.returncode != 0:
        raise RuntimeError("docker build failed")
    _remove_old_images()


def _remove_old_images():
    """Drop images of earlier add-on versions (~100 MB each on the SD card)."""
    repository = IMAGE.split(":")[0]
    listing = _docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}", repository)
    for image in listing.stdout.split():
        if image != IMAGE:
            utils.log(f"removing old image {image}")
            _docker("image", "rm", image)


class Container:
    """One Soloist container run; calls on_exit(returncode) when it ends."""

    def __init__(self, on_exit):
        self._on_exit = on_exit
        self._stopping = False
        _docker("rm", "-f", CONTAINER)
        command = [
            DOCKER, "run", "--rm", "-i",
            "--name", CONTAINER,
            "--network", "host",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=16m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "512m",
            "--pids-limit", "256",
            "-v", f"{VOLUME}:/data",
            "-v", f"{PULSE_SOCKET}:/run/pulse/native",
            "-e", "PULSE_SERVER=unix:/run/pulse/native",
            "-e", "PULSE_SINK=soloist",
            "-e", f"SOLOIST_NAME={utils.get_setting('device_name')}",
            "-e", f"SOLOIST_VOLUME={initial_volume()}",
            "-e", f"SOLOIST_CACHE_MB={utils.get_setting('cache_mb')}",
            "-e", f"SOLOIST_WS=127.0.0.1:{utils.get_setting('ws_port')}",
            IMAGE,
        ]
        # Explicit UTF-8: Kodi's Python runs with an ASCII locale on LibreELEC,
        # and Soloist's log contains non-ASCII text. A decode error would kill
        # _pump, and an undrained pipe eventually blocks Soloist.
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
        self._process.stdin.write(f"{read_api_key()}\n{_read_cookie()}\n")
        self._process.stdin.close()
        self._pump_thread = threading.Thread(target=self._pump, daemon=True)
        self._pump_thread.start()

    def _pump(self):
        for line in self._process.stdout:
            line = line.rstrip()
            # Soloist reports the playing track every 10 s.
            chatty = ": playing spotify:" in line
            (utils.debug if chatty else utils.log)(f"soloist: {line}")
        returncode = self._process.wait()
        utils.log(f"container exited with {returncode}")
        if not self._stopping:
            self._on_exit(returncode)

    def stop(self):
        self._stopping = True
        _docker("stop", "-t", "2", CONTAINER)
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
        # Kodi waits for every add-on thread before it unloads the add-on.
        self._pump_thread.join(timeout=1)
