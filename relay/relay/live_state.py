"""Thread-safe live connection state. Nothing here is persisted."""

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock


LIVE_DASHBOARD_CHANNEL = "relay_live_dashboard"


def dashboard_channel(user_id):
    return f"relay_dashboard_{user_id}"


def tally_lights_channel(credential_user_id):
    return f"relay_tally_lights_{credential_user_id}"


class RelayRegistry:
    def __init__(self):
        self._lock = Lock()
        self._tally_lights = {}
        self._transmitters = {}

    def connect_tally_light(self, device_id, channel, credential_user_id, settings):
        with self._lock:
            if device_id in self._tally_lights:
                return False
            self._tally_lights[device_id] = {
                "channel": channel, "credential_user_id": credential_user_id,
                "settings": deepcopy(settings), "pending": {},
            }
            return True

    def disconnect_tally_light(self, device_id, channel):
        with self._lock:
            tally_light = self._tally_lights.get(device_id)
            if tally_light and tally_light["channel"] == channel:
                del self._tally_lights[device_id]
                return True
            return False

    def tally_light(self, device_id):
        with self._lock:
            value = self._tally_lights.get(device_id)
            return deepcopy(value) if value else None

    def tally_lights(self):
        with self._lock:
            return deepcopy(self._tally_lights)

    def begin_settings(self, device_id, operation_id, changes, credential_user_id):
        with self._lock:
            tally_light = self._tally_lights.get(device_id)
            if not tally_light or tally_light["credential_user_id"] != credential_user_id:
                return None
            tally_light["pending"] = {"id": operation_id, "changes": deepcopy(changes)}
            return tally_light["channel"]

    def finish_settings(self, device_id, operation_id, state):
        with self._lock:
            tally_light = self._tally_lights.get(device_id)
            if not tally_light or tally_light["pending"].get("id") != operation_id:
                return False
            if state == "applied":
                self._merge(tally_light["settings"], tally_light["pending"]["changes"])
            tally_light["pending"] = {}
            return state == "applied"

    @staticmethod
    def _merge(target, changes):
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key].update(value)
            else:
                target[key] = value

    def connect_transmitter(self, channel, credential_user_id):
        with self._lock:
            if credential_user_id in self._transmitters:
                return False
            self._transmitters[credential_user_id] = {
                "channel": channel, "credential_user_id": credential_user_id,
                "program": None, "preview": None, "sequence": -1, "updated_at": None,
            }
            return True

    def disconnect_transmitter(self, channel, credential_user_id):
        with self._lock:
            transmitter = self._transmitters.get(credential_user_id)
            if transmitter and transmitter["channel"] == channel:
                del self._transmitters[credential_user_id]
                return True
            return False

    def set_atem_state(self, channel, credential_user_id, program, preview, sequence):
        with self._lock:
            transmitter = self._transmitters.get(credential_user_id)
            if (not transmitter or transmitter["channel"] != channel
                    or sequence <= transmitter["sequence"]):
                return False
            transmitter.update(program=program, preview=preview, sequence=sequence,
                               updated_at=datetime.now(timezone.utc).isoformat())
            return True

    def transmitter(self, credential_user_id):
        with self._lock:
            transmitter = self._transmitters.get(credential_user_id)
            return deepcopy(transmitter) if transmitter else None

    def hardware_channels(self, credential_user_id):
        with self._lock:
            channels = [tally_light["channel"] for tally_light in self._tally_lights.values()
                        if tally_light["credential_user_id"] == credential_user_id]
            transmitter = self._transmitters.get(credential_user_id)
            if transmitter:
                channels.append(transmitter["channel"])
            return channels

    def snapshot(self, credential_user_id):
        with self._lock:
            transmitter = self._transmitters.get(credential_user_id)
            program = transmitter["program"] if transmitter else None
            preview = transmitter["preview"] if transmitter else None
            tally_lights = []
            for device_id, tally_light in self._tally_lights.items():
                if tally_light["credential_user_id"] != credential_user_id:
                    continue
                settings = tally_light["settings"]
                status = ("no-transmitter" if not transmitter else
                          "program" if settings["source"] == program else
                          "preview" if settings["source"] == preview else "standby")
                tally_lights.append({"deviceId": device_id, "name": settings["name"],
                                     "source": settings["source"], "status": status,
                                     "settings": deepcopy(settings)})
            tally_lights.sort(key=lambda item: (item["source"], item["deviceId"]))
            return {"transmitter_online": bool(transmitter), "program": program,
                    "preview": preview,
                    "updated_at": transmitter["updated_at"] if transmitter else None,
                    "tally_lights": tally_lights}


registry = RelayRegistry()
