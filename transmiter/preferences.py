"""Local application preferences and atomic persistence."""

import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from errors import AppError
from relay_profile import relay_urls, validate_token


def program_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "TallyLights"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TallyLights"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "TallyLights"


def validate_default_wifi(ssid, password):
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32:
        raise AppError("Default Wi-Fi name must contain 1–32 UTF-8 bytes.")
    if not isinstance(password, str) or not 1 <= len(password.encode("utf-8")) <= 63:
        raise AppError("Default Wi-Fi password must contain 1–63 UTF-8 bytes.")


def default_preferences():
    return {"version": 5, "setup": "unconfigured", "relay_url": "",
            "transmitter_token": "", "tally_light_token": "",
            "default_wifi_ssid": "", "default_wifi_password": "",
            "last_atem_ip": ""}


class PreferenceStore:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else program_data_dir()
        self.file = self.folder / "settings.json"

    def load(self):
        if not self.file.exists():
            return default_preferences()
        try:
            value = json.loads(self.file.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("version") not in (2, 3, 4, 5)
                    or value.get("setup") not in ("unconfigured", "skipped", "configured")):
                raise ValueError("Unrecognized settings format")
            if value["setup"] == "configured":
                relay_urls(value["relay_url"])
                for field in ("transmitter_token", "tally_light_token"):
                    validate_token(value[field], field)
            current = default_preferences()
            loaded = {**current, **{key: item for key, item in value.items() if key in current},
                      "version": 5}
            if loaded["setup"] == "skipped":
                loaded["setup"] = "unconfigured"
            if loaded["default_wifi_ssid"] or loaded["default_wifi_password"]:
                validate_default_wifi(
                    loaded["default_wifi_ssid"], loaded["default_wifi_password"])
            return loaded
        except (OSError, UnicodeError, ValueError, KeyError) as exc:
            raise AppError(f"Could not read saved preferences: {exc}") from exc

    def save(self, value):
        self.folder.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.folder.chmod(0o700)
        temporary = self.folder / f".{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                temporary.chmod(0o600)
            temporary.replace(self.file)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self):
        target = self.folder.resolve()
        if (target == target.parent or target == Path.home().resolve()
                or target.name != "TallyLights"):
            raise AppError("Refusing to clear an unexpected application data folder.")
        if target.exists():
            shutil.rmtree(target)


