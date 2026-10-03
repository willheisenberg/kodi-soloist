import xbmc
import xbmcaddon
import xbmcgui

_ADDON = xbmcaddon.Addon()
ADDON_ID = _ADDON.getAddonInfo("id")
ADDON_NAME = _ADDON.getAddonInfo("name")
ADDON_PATH = _ADDON.getAddonInfo("path")
ADDON_VERSION = _ADDON.getAddonInfo("version")
_ADDON_ICON = _ADDON.getAddonInfo("icon")

_DEFAULTS = {
    "device_name": "Kodi",
    "initial_volume": "80",
    "cache_mb": "500",
    "dnd_kodi": "false",
    "pin_volume": "false",
    "ws_port": "24879",
    "rtp_port": "23433",
}


def get_setting(key):
    value = xbmcaddon.Addon().getSetting(key)
    return value if value else _DEFAULTS[key]


def get_bool(key):
    return get_setting(key) == "true"


def string(string_id):
    return xbmcaddon.Addon().getLocalizedString(string_id)


def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}: {message}", level)


def debug(message):
    """Chatty per-event output; visible with Kodi's debug logging enabled."""
    log(message, xbmc.LOGDEBUG)


def notification(message, heading=ADDON_NAME, icon=_ADDON_ICON, time=5000):
    xbmcgui.Dialog().notification(heading, message, icon, time, False)
