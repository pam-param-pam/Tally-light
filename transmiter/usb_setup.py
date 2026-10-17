"""USB serial client for USB_SETUP_PROTOCOL.md. Passwords are never logged."""

import json
import time
from uuid import uuid4

from setup_validation import InvalidSettings, validate_changes


class SetupError(Exception):
    pass


class NoReply(SetupError):
    pass


class FirmwareCrash(SetupError):
    pass


def available_ports():
    from serial.tools import list_ports

    return [(port.device, port.description) for port in list_ports.comports()]


def exchange(port_name, command, data, *, serial_factory=None, boot_wait=1.5, timeout=6):
    """Send one command and return its matching response, ignoring ESP boot text."""
    if not port_name:
        raise SetupError("Choose a USB serial port.")
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial

    request_id = uuid4().hex
    payload = json.dumps({"type": command, "id": request_id, "data": data}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 2048:
        raise SetupError("Settings are too long for the Tally Light USB protocol.")

    try:
        connection = serial_factory(port_name, baudrate=115200, timeout=0.25, write_timeout=2, rtscts=False, xonxoff=False)
        with connection:
            # USB-UART adapters can reset a NodeMCU when the port opens.
            connection.dtr = False
            connection.rts = False
            time.sleep(boot_wait)
            connection.reset_input_buffer()
            # Pace long frames for the ESP8266 UART receive buffer.
            wire = payload + b"\n"
            for offset in range(0, len(wire), 64):
                connection.write(wire[offset:offset + 64])
                if offset + 64 < len(wire):
                    time.sleep(0.03)
            connection.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = connection.read_until(b"\n", size=4096)
                if not line or len(line) > 4096:
                    continue
                if b"CUT HERE FOR EXCEPTION DECODER" in line or b"Exception (" in line:
                    raise FirmwareCrash("The Tally Light firmware crashed during USB setup. Flash the updated ESP8266 firmware.")
                try:
                    frame = json.loads(line)
                except (UnicodeDecodeError, ValueError):
                    continue  # ESP8266 ROM text is not part of the JSON protocol.
                if not isinstance(frame, dict) or frame.get("replyTo") != request_id:
                    continue
                if frame.get("type") == "setup.error":
                    raise SetupError(f"USB protocol error: {frame.get('data', {}).get('code', 'unknown')}")
                if frame.get("type") == "setup.result":
                    result = frame.get("data", {})
                    if result.get("state") == "rejected":
                        raise SetupError(f"The Tally Light rejected {result.get('field', 'settings')}.")
                    if result.get("state") != "saved":
                        raise SetupError("Unexpected USB setup result.")
                elif frame.get("type") != "setup.snapshot":
                    continue
                return frame
    except SetupError:
        raise
    except (OSError, ValueError) as exc:
        raise SetupError(f"Could not use {port_name}: {exc}") from exc
    raise NoReply("The Tally Light did not respond. Check the USB port and connect again.")


def read_settings(port_name, **kwargs):
    frame = exchange(port_name, "setup.get", {}, **kwargs)
    if frame.get("type") != "setup.snapshot" or not isinstance(frame.get("data", {}).get("settings"), dict):
        raise SetupError("The Tally Light returned invalid settings.")
    return frame


def write_settings(port_name, changes, *, saved_snapshot=None, **kwargs):
    if not isinstance(changes, dict) or not changes:
        raise SetupError("Enter settings to save.")
    snapshot = saved_snapshot if saved_snapshot is not None else read_settings(port_name, **kwargs)
    try:
        validate_changes(changes, snapshot["data"]["settings"])
    except InvalidSettings as exc:
        raise SetupError(str(exc)) from exc
    try:
        frame = exchange(port_name, "setup.set", changes, **kwargs)
    except NoReply:
        frame = None
    if frame is not None and frame.get("type") != "setup.result":
        raise SetupError("The Tally Light returned an invalid save response.")

    # Every USB save restarts the firmware. Reconnect and verify the complete
    # saved snapshot even when the pre-restart confirmation was received.
    time.sleep(2)
    try:
        verified = read_settings(port_name, **kwargs)
    except FirmwareCrash:
        raise
    except SetupError as exc:
        raise SetupError("Settings were sent, but the Tally Light could not be reconnected "
                         "for automatic verification.") from exc
    if not _matches_snapshot(verified["data"]["settings"], changes):
        raise SetupError("The Tally Light restarted, but its saved settings do not match.")
    verified["data"]["verified"] = True
    return verified


def _matches_snapshot(saved, changes):
    for key, value in changes.items():
        if key == "password":
            if saved.get("password") != value:
                return False
        elif isinstance(value, dict):
            if not isinstance(saved.get(key), dict) or not _matches_snapshot(saved[key], value):
                return False
        elif saved.get(key) != value:
            return False
    return True
