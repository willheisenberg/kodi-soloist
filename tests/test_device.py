import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))

import device


def test_playback_on_the_active_device_is_mirrored():
    d = device.Device()

    assert d.update({"type": "playback_state", "status": "playing", "is_active": True}) == "playing"
    assert d.update({"type": "playback_changed", "status": "paused"}) == "paused"


def test_playback_on_another_device_is_idle():
    d = device.Device()

    assert d.update({"type": "auth_state", "logged_in": True, "is_active": False}) == "idle"
    assert d.update({"type": "playback_state", "status": "playing", "is_active": False}) == "idle"
    # playback_changed carries no is_active of its own.
    assert d.update({"type": "playback_changed", "status": "playing"}) == "idle"


def test_release_turns_running_playback_idle():
    d = device.Device()
    d.update({"type": "playback_state", "status": "playing", "is_active": True})

    assert d.update({"type": "device_changed", "is_active": False}) == "idle"
    assert d.update({"type": "playback_changed", "status": "playing"}) == "idle"


def test_becoming_active_picks_up_the_status_reported_before():
    d = device.Device()
    d.update({"type": "playback_changed", "status": "playing"})

    assert d.update({"type": "device_changed", "is_active": True}) == "playing"


def test_unrelated_messages_keep_the_status():
    d = device.Device()
    d.update({"type": "playback_state", "status": "playing", "is_active": True})

    assert d.update({"type": "volume_changed", "volume": 80}) == "playing"
