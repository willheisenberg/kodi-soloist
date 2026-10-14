import json
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))


class _Addon:
    def getAddonInfo(self, key):
        return "service.soloist"

    def getSetting(self, key):
        return ""


def _module(name, **attributes):
    """Register a stand-in, or add missing attributes to one another test registered."""
    module = sys.modules.setdefault(name, types.ModuleType(name))
    for key, value in attributes.items():
        module.__dict__.setdefault(key, value)


# Kodi's Python API only exists inside Kodi.
_module("xbmc", LOGINFO=1, LOGDEBUG=0, LOGWARNING=2, log=lambda message, level=1: None)
_module("xbmcgui")
_module("xbmcaddon", Addon=_Addon)

import pulseaudio

SOURCES = [{"index": 23, "name": "soloist.monitor"}, {"index": 25, "name": "tv_hdmi.monitor"}]
SINKS = [{"index": 23, "name": "soloist"}, {"index": 24, "name": "tv_hdmi"}]


def _rtp_output(source, owner="48"):
    return {"index": 11, "owner_module": owner, "source": source}


def _spotify_input(sink):
    return {"index": 21, "sink": sink, "properties": {"application.process.binary": "soloist"}}


class _Pactl:
    """Answers pactl like the PulseAudio server on the Pi and records the moves."""

    def __init__(self, source_outputs, sink_inputs):
        self.lists = {
            "sources": SOURCES, "sinks": SINKS,
            "source-outputs": source_outputs, "sink-inputs": sink_inputs,
        }
        self.moves = []

    def __call__(self, *args, quiet=False):
        if args[:3] == ("-f", "json", "list"):
            return json.dumps(self.lists[args[3]])
        if args[0] in ("move-source-output", "move-sink-input"):
            self.moves.append(args)
        return ""


def _sink(monkeypatch, source_outputs, sink_inputs):
    pactl = _Pactl(source_outputs, sink_inputs)
    monkeypatch.setattr(pulseaudio, "_pactl", pactl)
    sink = pulseaudio.RtpSink.__new__(pulseaudio.RtpSink)
    sink.sink = "soloist"
    sink._modules = ["47", "48"]
    return sink, pactl


def test_correct_routing_moves_nothing(monkeypatch):
    sink, pactl = _sink(monkeypatch, [_rtp_output(23)], [_spotify_input(23)])
    sink.ensure_routed()
    assert pactl.moves == []


def test_moved_rtp_stream_is_moved_back(monkeypatch):
    sink, pactl = _sink(monkeypatch, [_rtp_output(25)], [_spotify_input(23)])
    sink.ensure_routed()
    assert pactl.moves == [("move-source-output", "11", "soloist.monitor")]


def test_moved_spotify_stream_is_moved_back(monkeypatch):
    sink, pactl = _sink(monkeypatch, [_rtp_output(23)], [_spotify_input(24)])
    sink.ensure_routed()
    assert pactl.moves == [("move-sink-input", "21", "soloist")]


def test_foreign_rtp_stream_is_left_alone(monkeypatch):
    sink, pactl = _sink(monkeypatch, [_rtp_output(23), _rtp_output(25, owner="99")], [])
    sink.ensure_routed()
    assert pactl.moves == []


def test_pactl_failure_moves_nothing(monkeypatch):
    sink, pactl = _sink(monkeypatch, [], [])
    monkeypatch.setattr(pulseaudio, "_pactl", lambda *args, quiet=False: "")
    sink.ensure_routed()
    assert pactl.moves == []
