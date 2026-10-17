import json

from ..live_state import registry, tally_lights_channel
from ..protocol.frames import FrameType
from ..protocol.settings import InvalidField, valid_device, validate_settings
from .base import AuthenticatedConsumer
from .dashboard import publish_live_state


class TallyLightConsumer(AuthenticatedConsumer):
    credential_role = "tally_light"
    credential_name = "Tally Light"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_id = None

    @property
    def response_device_id(self):
        return self.device_id

    async def validate_hello(self, frame):
        if frame["type"] == FrameType.HELLO and valid_device(frame["deviceId"]):
            return True
        await self.error("invalid_field", "Expected hello with deviceId", frame)
        await self.close(code=4400, reason="Expected hello with a valid deviceId")
        return False

    async def register(self, frame, owner_id):
        reported = frame["data"]["settings"]
        try:
            validate_settings(reported)
        except InvalidField as exc:
            await self.error("invalid_field", str(exc), frame, exc.field)
            await self.close(code=4400, reason=f"{exc.field}: {exc}")
            return False
        if not registry.connect_tally_light(frame["deviceId"], self.channel_name, owner_id, reported):
            await self.error("busy", "Device ID already connected", frame)
            await self.close(code=4409, reason="Device ID already connected")
            return False
        self.device_id = frame["deviceId"]
        await self.channel_layer.group_add(tally_lights_channel(owner_id), self.channel_name)
        await publish_live_state(self.channel_layer)
        return True

    async def after_authentication(self, frame=None):
        state = registry.transmitter(self.user_id)
        if state:
            await self.send_frame(
                FrameType.ATEM_STATE,
                {key: state[key] for key in ("program", "preview", "sequence")})

    async def handle_authenticated_frame(self, frame):
        if frame["deviceId"] != self.device_id:
            await self.error("invalid_field", "Wrong device ID", frame)
            return
        if frame["type"] == FrameType.SETTINGS_RESULT:
            state = frame["data"]["state"]
            reply_to = frame["replyTo"]
            if state not in ("applied", "restarting", "rejected") or not isinstance(reply_to, str):
                await self.error("invalid_field", "Invalid settings result", frame)
                return
            if registry.finish_settings(self.device_id, reply_to, state):
                await publish_live_state(self.channel_layer)
        elif frame["type"] != FrameType.ERROR:
            await self.error("unsupported_type", "Unknown Tally Light message", frame)

    async def deliver_atem(self, event):
        tally_light = registry.tally_light(self.device_id)
        if self.ready and tally_light:
            await self.send(text_data=json.dumps(event["frame"], separators=(",", ":")))

    async def deliver_settings(self, event):
        if self.ready and event["device_id"] == self.device_id:
            await self.send(text_data=json.dumps(event["frame"], separators=(",", ":")))

    async def cleanup_connection(self):
        if self.device_id:
            disconnected = registry.disconnect_tally_light(self.device_id, self.channel_name)
            await self.channel_layer.group_discard(
                tally_lights_channel(self.user_id), self.channel_name)
            if disconnected:
                await publish_live_state(self.channel_layer)
