from uuid import uuid4

from ..live_state import registry, tally_lights_channel
from ..protocol.frames import FrameType
from .base import AuthenticatedConsumer
from .dashboard import publish_live_state


class TransmitterConsumer(AuthenticatedConsumer):
    credential_role = "transmitter"
    credential_name = "transmitter"

    async def register(self, frame, owner_id):
        if not registry.connect_transmitter(self.channel_name, owner_id):
            await self.error("busy", "A transmitter is already connected", frame)
            await self.close(code=4409, reason="A transmitter is already connected")
            return False
        await publish_live_state(self.channel_layer)
        return True

    async def handle_authenticated_frame(self, frame):
        if frame["type"] != FrameType.ATEM_STATE:
            await self.error("unsupported_type", "Expected atem.state", frame)
            return
        data = frame["data"]
        if (set(data) != {"program", "preview", "sequence"}
                or type(data["sequence"]) is not int or data["sequence"] < 0
                or any(value is not None and (type(value) is not int or not 1 <= value <= 65535)
                       for value in (data["program"], data["preview"]))):
            await self.error("invalid_field", "Invalid ATEM state", frame)
            return
        if registry.set_atem_state(self.channel_name, self.user_id, data["program"],
                                   data["preview"], data["sequence"]):
            await self.channel_layer.group_send(tally_lights_channel(self.user_id),
                                                {"type": "deliver_atem", "frame": frame})
            await publish_live_state(self.channel_layer)

    async def cleanup_connection(self):
        if registry.disconnect_transmitter(self.channel_name, self.user_id):
            frame = {"type": FrameType.ATEM_STATE, "id": uuid4().hex,
                     "data": {"program": None, "preview": None, "sequence": 0}}
            await self.channel_layer.group_send(tally_lights_channel(self.user_id),
                                                {"type": "deliver_atem", "frame": frame})
            await publish_live_state(self.channel_layer)
