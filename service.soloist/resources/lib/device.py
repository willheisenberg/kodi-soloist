"""Tell this box's playback apart from playback elsewhere on the account.

Soloist reports the account's playback state even while another device (the
phone) is the active one: `status` is "playing" then, with `is_active` false.
Only the active device's status may drive Kodi. No Kodi imports here, so the
module is testable outside Kodi.
"""

_STATUS_MESSAGES = ("playback_state", "playback_changed")


class Device:
    def __init__(self):
        self._active = False
        self._status = "idle"

    def update(self, message):
        """Take in one Soloist message; return the status Kodi should mirror.

        Not every message carries `is_active`, and the status may arrive
        before the device becomes active, so both are remembered.
        """
        if "is_active" in message:
            self._active = bool(message["is_active"])
        if message.get("type") in _STATUS_MESSAGES:
            self._status = message.get("status") or "idle"
        return self._status if self._active else "idle"
