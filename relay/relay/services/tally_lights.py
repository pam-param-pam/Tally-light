from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ..live_state import registry
from ..protocol.frames import FrameType
from ..protocol.settings import InvalidField, merge_settings
from .errors import ServiceError


class TallyLightService:
    @staticmethod
    def connected_tally_lights(user_id):
        items = [{"deviceId": device_id, "online": True, "settings": tally_light["settings"]}
                 for device_id, tally_light in registry.tally_lights().items()
                 if tally_light["credential_user_id"] == user_id]
        return sorted(items, key=lambda item: item["deviceId"])

    @staticmethod
    def live_snapshot(user_id):
        return registry.snapshot(user_id)

    @staticmethod
    def update_tally_light_settings(user_id, device_id, changes):
        tally_light = registry.tally_light(device_id)
        if tally_light is None or tally_light["credential_user_id"] != user_id:
            raise ServiceError("Tally Light must be online to change settings.")
        try:
            merge_settings(tally_light["settings"], changes)
        except InvalidField as exc:
            raise ServiceError(str(exc), exc.field) from exc
        operation_id = uuid4().hex
        channel = registry.begin_settings(device_id, operation_id, changes, user_id)
        if channel is None:
            raise ServiceError("Tally Light must be online to change settings.")
        frame = {"type": FrameType.SETTINGS_SET, "id": operation_id, "deviceId": device_id,
                 "data": changes}
        async_to_sync(get_channel_layer().send)(channel, {
            "type": "deliver_settings", "device_id": device_id, "frame": frame,
        })
        return {"deviceId": device_id, "state": "pending", "operationId": operation_id}

    @classmethod
    def update_all_brightness(cls, user_id, brightness):
        tally_lights = cls.connected_tally_lights(user_id)
        if not tally_lights:
            raise ServiceError("No Tally Lights are connected.")
        return {
            "updates": [cls.update_tally_light_settings(user_id, tally_light["deviceId"],
                                                        {"brightness": brightness})
                        for tally_light in tally_lights]
        }
