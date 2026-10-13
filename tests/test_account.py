import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))

import account


def test_login_gives_the_username():
    assert account.parse("2026-10-13 18:48:47.261: logged in as jane.doe") == "jane.doe"
    assert account.parse("2026-10-13 16:26:25.412: logged in as 1234567890\n") == "1234567890"


def test_logout_gives_an_empty_name():
    assert account.parse("2026-10-13 16:26:25.412: logged out") == ""


def test_other_lines_are_ignored():
    assert account.parse("2026-10-13 16:26:26.087: became active device") is None
    assert account.parse("soloist 1.3.8.105 build 1790942580 (linux/aarch64)") is None


def test_a_track_title_cannot_log_anyone_in():
    line = '2026-10-13 18:05:37.622: paused spotify:track:0b62 "x: logged in as eve" by "y" [2:55 / 4:08]'
    assert account.parse(line) is None
    assert account.parse('2026-10-13 18:05:37.622: playing spotify:track:0b62 "logged out"') is None
