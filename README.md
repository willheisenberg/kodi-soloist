![Soloist for Kodi](assets/banner.png)

# Soloist for Kodi

**English** · [Deutsch](README.de.md)

**Spotify Connect for Kodi on LibreELEC: the box shows up as a device in the
Spotify app, and the music plays through Kodi, with title and cover art on the
TV.**

It is built on [Spotify Soloist](https://developer.spotify.com/documentation/soloist),
Spotify's official headless client. librespot-based solutions often fail with
an "Audio key error" on newly created Spotify accounts. Soloist, being the
official client, should not be affected by that.

> This add-on is an unofficial project and is not affiliated with Spotify.
> Soloist itself is proprietary software by Spotify and is downloaded directly
> from Spotify at runtime. It is not part of this repository.

---

## Requirements

| | |
|---|---|
| Device | Raspberry Pi 5 (aarch64), tested. aarch64, armv7 and x86_64 should work. |
| System | LibreELEC 12 with Kodi 21 "Omega" |
| Add-on | **Docker** (`service.system.docker`) from the LibreELEC repository |
| Spotify | a **Soloist API key**, created with a Premium account. According to Spotify, Free accounts can connect afterwards as well. |

## Installation

1. **Create an API key:** log in at
   <https://developer.spotify.com/dashboard/soloist> with the Premium account
   and create a key.
2. **Store the key on the box** without it ending up in the shell history:
   ```
   mkdir -p /storage/.config/soloist && chmod 700 /storage/.config/soloist
   read -rs KEY && printf '%s' "$KEY" > /storage/.config/soloist/api_key && unset KEY
   chmod 600 /storage/.config/soloist/api_key
   ```
   After `read`, paste the key and press Enter. Nothing is shown while you do.
3. **Install the repository:** download
   [`repository.soloist-1.0.0.zip`](https://github.com/willheisenberg/kodi-soloist/raw/main/repo/repository.soloist/repository.soloist-1.0.0.zip)
   and copy it to the box. In Kodi, allow
   **Settings → System → Add-ons → Unknown sources** once, then use
   **Add-ons → Install from zip file**.
4. **Install the add-on:** **Add-ons → Install from repository → Soloist
   Repository → Services → Soloist**. Updates then arrive automatically.

It also works without the repository: install the latest
`service.soloist-*.zip` from the
[releases](https://github.com/willheisenberg/kodi-soloist/releases) as a zip
file. Updates then have to be installed by hand.

On first start the add-on builds the container image `kodi-soloist:<version>`.
On a Pi 5 this takes about a minute. After that the box appears in the Spotify
app under "Devices" as **Kodi**.

## Usage

- **In the Spotify app**, pick the box as the device and play. Kodi shows
  title, artist and cover art.
- **Pause, next and stop in Kodi** are passed on to Spotify.
- **If Kodi starts something else**, such as a video, Spotify pauses.
- **In Kodi**, Soloist is listed under the program add-ons. A click shows the
  status ("Playing: …", "Ready …") and offers *Release Spotify device* and
  *Settings*. The service itself is under *My add-ons → Services*.
- **Volume:** by default the Spotify app controls the volume. If you only want
  to use the receiver, turn on *Always keep volume at 100%* in the settings.
  If someone then moves the slider in the app, it jumps back.

## Settings

| Setting | Default | |
|---|---|---|
| Device name in the Spotify app | `Kodi` | Name shown in the Spotify app |
| Always keep volume at 100% | off | On: Soloist stays at 100%, only the receiver controls the volume |
| Initial volume | 80% | only visible while the volume is not kept at 100% |
| Don't interrupt other Kodi playback | off | On: Spotify pauses as long as Kodi plays something else |
| Cache size | 500 MB | *Advanced* |
| WebSocket port / RTP port | 24879 / 23433 | *Advanced*, localhost only. Do not change the RTP port if the PartyQueue bot is running. |

## Working together with the PartyQueue bot

With [KodiMediaBot](https://github.com/willheisenberg/KodiMediaBot), the bot
and Spotify can interrupt each other without anything getting lost:

- **Spotify takes over:** the bot parks its queue or remembers the radio
  station that is playing. The panel shows `Spotify: title – artist`.
- **Spotify is gone or stays paused for 30 seconds:** the bot resumes the
  interrupted video at the old position or restarts the station.
- **Stop in the bot, or the bot plays something itself:** the box releases the
  Spotify device, and the app moves playback back to the phone. As long as
  another device is playing, the add-on leaves Kodi alone.

For this, the add-on and the bot send each other Kodi notifications:

| Direction | Message | Meaning |
|---|---|---|
| Add-on → clients | `Other.soloist_takeover` (sender `service.soloist`) | Spotify is about to start, sent *before* Kodi reports the previous item as stopped |
| Client → add-on | `JSONRPC.NotifyAll` with `message: "soloist_release"` | Release the Spotify device (`deactivate`); the client stops or replaces the Spotify stream in Kodi itself |

## Architecture

```
Spotify app ──Connect──▶ Soloist (Docker container, isolated)
                            │ PulseAudio (sink "soloist")
                            ▼
                   module-rtp-send ──▶ rtp://127.0.0.1:23433 ──▶ Kodi player
                            ▲
   Kodi add-on ◀──WebSocket 127.0.0.1:24879── title, cover, status
```

- **Soloist is closed source** and therefore runs in a container: as a normal
  user (uid 1000), with a read-only file system, without capabilities and
  with `no-new-privileges`. It only gets the PulseAudio socket, its own volume
  `soloist-data` and the host network, which Spotify Connect needs to be
  discovered on the Wi-Fi. It cannot reach `/storage`, tokens of other
  services or Docker.
- **The binary is not included in the add-on**, because Spotify forbids
  redistribution. The container downloads it from Spotify's CDN on every
  start. Builds expire after 90 days (exit code 10); a restart is then enough.
- **Secrets** (API key, PulseAudio cookie) are passed into the container via
  stdin, not as a Docker argument or a mounted file. Because Soloist only
  accepts the key as a command-line argument, it is visible in `ps` on the box
  while running, and only to root.
- Forwarding the audio via a PulseAudio sink and RTP comes from the
  [librespot add-on by LibreELEC](https://github.com/LibreELEC/LibreELEC.tv/tree/master/packages/addons/service/librespot)
  (GPL-2.0-only).

## Troubleshooting

The most important events are in `kodi.log` with the prefix
`service.soloist:`. Every command sent to Soloist and every event from Soloist
only shows up with debug logging enabled in Kodi.

## Development

```
python -m pytest -q     # tests for the parts that work without Kodi (WebSocket, metadata)
ruff check .
./scripts/build-zip.sh  # dist/service.soloist-<version>.zip
./scripts/build-repo.sh # repo/: Kodi repository with the current versions
```

A release reaches the users of the repository once the version in
`service.soloist/addon.xml` is bumped, `./scripts/build-repo.sh` has run and
`repo/` is pushed to `main`.

Kodi on LibreELEC 12 ships Python 3.11, and the code has to stay compatible
with it. Icon, fanart and banner are generated from the SVG files in `assets/`.

## License

GPL-2.0-only, see [LICENSE](LICENSE).
