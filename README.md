# Tally Light

Wireless Tally Lights for ATEM switchers. The transmitter runs on the ATEM network and sends program and preview state to the relay. Each Tally Light connects to the relay over a WebSocket and receives that state.

## Getting started

1. Download the transmitter application from the [latest GitHub release](https://github.com/pam-param-pam/Tally-light/releases/latest), or run it from source as described below.
2. Download a **connection profile** from the dashboard and import it into the transmitter. The app verifies the transmitter token before saving the profile.
3. Connect your first Tally Light over USB and configure its Wi-Fi, name, and ATEM input number.
4. Start the transmitter with your ATEM selected, then open **View live** in the dashboard to see the transmitter and connected Tally Lights.

The transmitter must be on the ATEM network. Tally Lights need network access to the relay. Firmware supports relay connections only; it does not connect directly to the ATEM.

## Transmitter application

Download `Tally-Transmitter.exe` from the [latest GitHub release](https://github.com/pam-param-pam/Tally-light/releases/latest) on Windows. To run from source, install dependencies with `pip install -r transmiter/requirements.txt`, then run `python transmiter/gui.py` (or the PyCharm **transmiter** run configuration).

The `Build Tally Transmitter` GitHub Actions workflow can also be run manually to produce a downloadable workflow artifact. Pushing a tag whose name starts with `v`, such as `v1.0.0`, builds the Windows executable, creates the corresponding GitHub release if needed, and attaches `Tally-Transmitter.exe` to it.

Open **Settings** to import or replace the connection profile, save default Tally Light Wi-Fi details, or clear saved application data. On Windows, settings are stored in `%LOCALAPPDATA%\TallyLights\settings.json`; on macOS, in `~/Library/Application Support/TallyLights/settings.json`; and on Linux, in `${XDG_CONFIG_HOME:-~/.config}/TallyLights/settings.json`.

In **Configure a Tally Light**, connect a NodeMCU by USB, select its serial port, and click **Connect to Tally Light**. Its settings appear only after the connection succeeds. **Use default Wi-Fi** copies the Wi-Fi details saved under **Settings**. Saving restarts the firmware, reconnects automatically, and verifies the saved settings. The app supplies the relay URL and Tally Light token from the connection profile. In **Run transmitter**, choose an ATEM or configure the mock source range and cue interval in milliseconds. A running mock transmitter can be paused and resumed without disconnecting it from the relay. The app uses the [USB setup protocol](USB_SETUP_PROTOCOL.md); USB setup remains available if Wi-Fi or relay access fails.

The built-in **Serial monitor** is configured for the Tally Light firmware at 115200 baud, 8N1, with flow control disabled. It can display live serial output and send newline-terminated commands. Disconnect it before reading or saving Tally Light settings over USB.

For the Tally Light, I used NODEMCU v3 esp8266 esp-12e, a Li-Pol rechargeable battery, and a charger. Older builds also have a setup button, which this firmware does not use. The original hardware cost was under $15.

## Dashboard

- **Home** links to the transmitter's GitHub releases and walks through importing a connection profile, configuring a Tally Light, and starting the transmitter.
- **View live** shows the transmitter connection and connected Tally Lights. Edit an individual Tally Light's settings or brightness, or use the shared brightness slider to update all connected Tally Lights.
- **Account settings** lets you change your username or password and generate or rotate the connection profile.
- **Tally Light colors** explains status indicators; **FAQ** contains setup and troubleshooting help.

Live state arrives over `/ws/dashboard` as connections and settings change, without periodic HTTP polling. Standby appears gray in the dashboard; the physical Tally Light LED is off.

## Relay server setup

From the repository root, install the relay dependencies:

```powershell
pip install -r relay/requirements.txt
cd relay
```

Set `DJANGO_SECRET_KEY` to a private random value in the environment or a local `.env` file. For local HTTP development, set `DEBUG=True` so session cookies can work without HTTPS. Then run:

```powershell
python manage.py migrate
python manage.py create_relay_user NAME
python manage.py runserver 0.0.0.0:8000
```

The account command prompts for a password without putting it in shell history. Use a relay address reachable by both the transmitter and Tally Lights when generating the connection profile.

The current relay uses an in-memory connection registry and channel layer. Run it as a single process; restarting clears live state and clients must reconnect.

### Connection profiles and rotation

The JSON connection profile contains `relay_url`, `transmitter_token`, and `tally_light_token`. Tokens are generated with cryptographically secure randomness, and the relay stores only adaptive password hashes. Treat the downloaded profile as a secret.

Plaintext tokens are returned only when generated. Downloading a replacement profile requires rotating both tokens, entering your current password, and confirming the warning. Rotation invalidates the previous profile and disconnects existing hardware clients. Import the replacement profile into the transmitter and upload settings to each Tally Light over USB to install its new token.

### WebSocket connections

The relay accepts JSON frames on `/ws/lights` and `/ws/transmitters`. Each client begins with `hello` using its role-specific token. The relay replies with `welcome`. Transmitters send `atem.state`; Tally Lights answer `settings.set` requests with `settings.result`. See [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md) for details.

Hardware clients must authenticate with a valid `hello` within 2.5 seconds. The dashboard authenticates using its Django session when connecting. Both authentication flows are rechecked every 30 seconds and use application-level JSON `ping`/`pong` messages. The relay waits up to 5 seconds for a matching pong; a missed reply closes the connection. Changing an account password invalidates its open dashboard connections.

Closing a connection immediately marks it inactive, removes its live state, and notifies the dashboard. Queued cues are ignored after closure begins. Transport send failures and unexpected consumer exits also run cleanup, preventing disconnected Tally Lights from remaining listed as connected.

The relay does not store Tally Lights in the database. Device settings and connection state exist only in memory while a Tally Light is connected. Each account may connect one transmitter, whose ATEM state is sent to that account's Tally Lights. Dashboard JSON endpoints use Django sessions, CSRF protection, and cache-backed request throttling.

## Firmware

The firmware is in `esp8266/ATEM_tally_light`, with bundled libraries in `esp8266/libraries`. Flash the current firmware when upgrading from an older protocol or settings layout. The old `/tally` and `/atem` WebSocket paths are no longer supported.

The firmware uses an EEPROM layout that resets settings if a device has an older layout. Use USB setup to enter the Wi-Fi name and password, relay URL, and Tally Light token.

There are no built-in Wi-Fi credentials or static IP settings. Connection indicators are steady colors, and USB activity does not change the LED:

| Color | Meaning |
| --- | --- |
| Red | Program |
| Green | Preview |
| Off | Standby |
| Yellow | No ATEM signal |
| Blue | Connecting to Wi-Fi |
| Pink | Connecting to the relay |

## Troubleshooting

- **Ping timeout:** the relay did not receive a matching JSON pong within the timeout. Check the Tally Light's Wi-Fi and relay connectivity, and use the serial monitor to inspect firmware output.
- **Stale connected entries after upgrading:** restart the relay once to clear entries left in memory by an older version.
- **Authentication fails after rotating credentials:** import the new connection profile and upload settings to each Tally Light again.
- **USB settings cannot be read:** close the serial monitor and any other application using the port, then reconnect through **Connect to Tally Light**.

## Code layout

- `relay/`: Django dashboard, function-based API views, services, serializers, protocol validation, and WebSocket consumers.
- `transmiter/`: desktop application and backend modules.
- `esp8266/ATEM_tally_light/`: firmware, USB setup, settings storage, relay client, and diode state management.
- [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md): relay WebSocket protocol.
- [USB_SETUP_PROTOCOL.md](USB_SETUP_PROTOCOL.md): USB configuration protocol.

### Transmitter code

Run `python transmiter/gui.py`. The GUI builds widgets and displays backend events. `app_backend.py` owns background jobs, USB access, serial monitoring, and application actions. `preferences.py` handles saved settings; `relay_profile.py` validates connection profiles and checks relay authentication. `cue_sources.py` implements ATEM and mock cue generation, while `transmitter.py` maintains the relay WebSocket and sends cues. USB protocol handling, settings validation, serial monitoring, and network discovery remain in their dedicated modules.

### Parts used

- [Nodemcu v2](https://botland.com.pl/moduly-wifi-esp8266/4450-modul-wifi-esp-12e-nodemcu-v2-4mb-5903351241328.html)
- [Li-Pol battery](https://botland.com.pl/akumulatory-li-pol-1s-37v/15613-akumulator-li-pol-akyga-1000mah-1s-37v-zlacze-jst-bec-gniazdo-48x30x7mm-5904422324230.html)
- [Li-Pol battery charger](https://botland.com.pl/moduly-ladowania-lipol-usb-micro-usb/16979-ladowarka-li-pol-tp4056-pojedyncza-cela-1s-37v-usb-typ-c-z-zabezpieczeniami--5904422326708.html)
- [RGB LED](https://botland.com.pl/diody-led-rgb/1667-dioda-led-5mm-rgb-matowa-wsp-katoda-5-szt-5903351244152.html)
- wires
- few resistors 10/22/44 ohm for RGB Led

### esp8266 code based on

- [@AronHetLam's Tally Light](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

