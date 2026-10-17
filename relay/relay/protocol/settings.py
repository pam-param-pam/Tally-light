import re
from copy import deepcopy
from urllib.parse import urlsplit


DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SETTINGS_FIELDS = {"name", "source", "brightness", "relay", "wifi"}
NESTED_FIELDS = {
    "relay": {"url"},
    "wifi": {"ssid", "password"},
}


class InvalidField(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def valid_device(value):
    return isinstance(value, str) and bool(DEVICE_RE.fullmatch(value))


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != SETTINGS_FIELDS:
        raise InvalidField("settings", "Expected the complete settings document")
    name, source, brightness = (settings[key] for key in ("name", "source", "brightness"))
    if not isinstance(name, str) or not 1 <= len(name) <= 30:
        raise InvalidField("name", "Must contain 1–30 characters")
    if type(source) is not int or not 1 <= source <= 255:
        raise InvalidField("source", "Must be a source number from 1 to 255")
    if type(brightness) is not int or not 0 <= brightness <= 255:
        raise InvalidField("brightness", "Must be 0–255")

    relay, wifi = (settings[key] for key in ("relay", "wifi"))
    for key, value in (("relay", relay), ("wifi", wifi)):
        expected = NESTED_FIELDS[key]
        if not isinstance(value, dict):
            raise InvalidField(key, "Expected an object")
        missing = expected - set(value)
        unexpected = set(value) - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append("Missing fields: " + ", ".join(f"{key}.{name}" for name in sorted(missing)))
            if unexpected:
                details.append("Unexpected fields: " + ", ".join(f"{key}.{name}" for name in sorted(unexpected)))
            raise InvalidField(key, "; ".join(details))
    url = relay["url"]
    if not isinstance(url, str) or not url or len(url) > 256:
        raise InvalidField("relay.url", "Invalid relay URL")
    try:
        parts = urlsplit(url)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        raise InvalidField("relay.url", "Invalid relay URL") from None
    if (parts.scheme not in ("ws", "wss") or not hostname or parts.path != "/ws/lights"
            or parts.username or parts.password or parts.query or parts.fragment
            or (port is not None and not 1 <= port <= 65535)):
        raise InvalidField("relay.url", "Expected ws:// or wss:// host/ws/lights")

    ssid = wifi["ssid"]
    if not isinstance(ssid, str) or not ssid or len(ssid) > 32:
        raise InvalidField("wifi.ssid", "Invalid Wi-Fi name")
    password = wifi["password"]
    if not isinstance(password, str) or not 1 <= len(password) <= 63:
        raise InvalidField("wifi.password", "Must contain 1–63 characters")
    return settings


def merge_settings(current, changes):
    if not isinstance(changes, dict) or not changes or set(changes) - SETTINGS_FIELDS:
        raise InvalidField("changes", "Unknown or empty settings update")
    merged = deepcopy(current)
    for key, value in changes.items():
        if key not in NESTED_FIELDS:
            merged[key] = value
            continue
        if not isinstance(value, dict) or not value or set(value) - NESTED_FIELDS[key]:
            raise InvalidField(key, "Unknown or empty nested settings update")
        for nested_key, nested_value in value.items():
            merged[key][nested_key] = nested_value
    return validate_settings(merged)
