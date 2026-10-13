"""Read the logged-in Spotify account from Soloist's log.

Soloist's WebSocket does not say whose account the box is on; only its log
does ("logged in as <username>"). Selecting the box in the Spotify app logs
it in as that account, so the last login is the account that is playing. No
Kodi imports here, so the module is testable outside Kodi.
"""

import re

# Anchored to the timestamp: track titles are logged too and may say anything.
_LINE = re.compile(r"^[\d-]+ [\d:.]+: (?:logged in as (?P<user>.+)|(?P<out>logged out))$")


def parse(line):
    """Return the username a log line logs in, "" for a logout, else None."""
    match = _LINE.match(line.strip())
    if not match:
        return None
    return "" if match.group("out") else match.group("user").strip()
