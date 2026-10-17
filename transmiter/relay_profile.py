"""Connection profile parsing and relay authentication."""

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from errors import AppError


def validate_token(token, field):
    if not isinstance(token, str) or not token.isascii() or not 32 <= len(token) <= 63:
        raise AppError(f"Connection profile contains an invalid {field}.")


def relay_urls(address):
    """Accept a server URL or either WebSocket endpoint; return both endpoints."""
    if not isinstance(address, str) or not address or address != address.strip():
        raise AppError("Enter a relay server URL.")
    try:
        parts = urlsplit(address)
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise AppError("Enter a valid relay server URL.") from exc
    if (parts.scheme not in ("ws", "wss", "http", "https") or not host
            or len(host.encode("utf-8")) > 63 or not re.fullmatch(r"[A-Za-z0-9._-]+", host)
            or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/", "/ws/lights", "/ws/transmitters")
            or parts.netloc.endswith(":") or (port is not None and not 1 <= port <= 65535)):
        raise AppError("Use a server URL or ws://host[:port]/ws/lights.")
    scheme = "wss" if parts.scheme in ("wss", "https") else "ws"
    authority = host + (f":{port}" if port is not None else "")
    return f"{scheme}://{authority}/ws/lights", f"{scheme}://{authority}/ws/transmitters"


def check_relay(lights_url, token):
    """Check reachability and token without taking the transmitter slot."""
    parts = urlsplit(lights_url)
    scheme = "https" if parts.scheme == "wss" else "http"
    check_url = f"{scheme}://{parts.netloc}/api/relay/check"
    request = Request(check_url, data=json.dumps({"token": token}).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
            if response.status != 200 or payload.get("ok") is not True:
                raise AppError("The server did not confirm the transmitter token.")
    except HTTPError as exc:
        if exc.code == 401:
            raise AppError("The relay rejected the transmitter token.") from exc
        if exc.code == 429:
            raise AppError("Too many attempts. Try again later.") from exc
        raise AppError(f"Relay validation failed (HTTP {exc.code}). Check the server URL.") from exc
    except (URLError, OSError, ValueError) as exc:
        raise AppError(f"Could not connect to the relay: {exc}") from exc


def load_connection_profile(filename):
    try:
        raw = Path(filename).read_bytes()
        if len(raw) > 4096:
            raise ValueError("file is too large")
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AppError(f"Could not read connection profile: {exc}") from exc
    expected = {"relay_url", "transmitter_token", "tally_light_token"}
    if not isinstance(document, dict) or set(document) != expected:
        raise AppError("Connection profile has an invalid format.")
    lights_url, _ = relay_urls(document["relay_url"])
    for field in ("transmitter_token", "tally_light_token"):
        validate_token(document[field], field)
    check_relay(lights_url, document["transmitter_token"])
    return {**document, "relay_url": lights_url}
