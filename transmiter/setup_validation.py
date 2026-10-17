from copy import deepcopy
from urllib.parse import urlsplit


class InvalidSettings(ValueError):
    pass


FIELDS = {"name", "source", "brightness", "relay", "wifi"}
NESTED_FIELDS = {
    "relay": {"url", "token"},
    "wifi": {"ssid", "password"},
}


def _text(value, field, limit):
    if not isinstance(value, str) or not 1 <= len(value.encode("utf-8")) <= limit:
        raise InvalidSettings(f"{field} must contain 1–{limit} UTF-8 bytes.")


def _relay_url(value):
    if value is None:
        return
    if not isinstance(value, str) or value != value.strip():
        raise InvalidSettings("relay.url must be a WebSocket URL.")
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise InvalidSettings("relay.url must be a WebSocket URL.") from exc
    if (parts.scheme not in ("ws", "wss") or not host or len(host.encode("utf-8")) > 63
            or ":" in host or " " in host or parts.netloc.endswith(":")
            or parts.path != "/ws/lights" or parts.username or parts.password
            or parts.query or parts.fragment or (port is not None and not 1 <= port <= 65535)):
        raise InvalidSettings("relay.url must be ws:// or wss://host[:port]/ws/lights.")


def validate_changes(changes, saved):
    """Check an update against the saved USB settings snapshot."""
    if not isinstance(changes, dict) or not changes or set(changes) - FIELDS:
        raise InvalidSettings("Unknown or empty settings update.")
    merged = deepcopy(saved)
    for field, value in changes.items():
        if field not in NESTED_FIELDS:
            merged[field] = value
            continue
        if not isinstance(value, dict) or not value or set(value) - NESTED_FIELDS[field]:
            raise InvalidSettings(f"{field} has unknown or empty fields.")
        for key, item in value.items():
            if key in ("password", "token"):
                _text(item, f"{field}.{key}", 63)
                merged[field][key] = item
            else:
                merged[field][key] = item

    _text(merged["name"], "name", 30)
    if type(merged["source"]) is not int or not 1 <= merged["source"] <= 255:
        raise InvalidSettings("source must be 1–255.")
    if type(merged["brightness"]) is not int or not 0 <= merged["brightness"] <= 255:
        raise InvalidSettings("brightness must be 0–255.")

    relay, wifi = (merged[key] for key in ("relay", "wifi"))

    _text(wifi["ssid"], "wifi.ssid", 32)
    if not wifi.get("password"):
        raise InvalidSettings("A Wi-Fi password is required.")
    _relay_url(relay["url"])
    if relay["url"] is None:
        raise InvalidSettings("A relay URL is required.")
    if not relay.get("token"):
        raise InvalidSettings("A Tally Light token is required.")
