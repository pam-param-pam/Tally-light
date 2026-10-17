import json
from importlib import import_module

from channels.auth import get_user
from django.conf import settings

from ..live_state import LIVE_DASHBOARD_CHANNEL, dashboard_channel, registry
from .base import AuthenticatedConsumer


SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


async def publish_live_state(channel_layer):
    await channel_layer.group_send(LIVE_DASHBOARD_CHANNEL, {
        "type": "live_state_changed",
    })


class DashboardConsumer(AuthenticatedConsumer):
    authenticate_on_connect = True

    async def authenticate_connection(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            return False
        self.session_key = self.scope["session"].session_key
        self.user_id = user.id
        return self.session_key is not None

    async def after_authentication(self, frame=None):
        await self.channel_layer.group_add(LIVE_DASHBOARD_CHANNEL, self.channel_name)
        await self.channel_layer.group_add(dashboard_channel(self.user_id), self.channel_name)
        await self.send_snapshot()

    async def authentication_is_valid(self):
        session = SessionStore(session_key=self.session_key)
        user = await get_user({"session": session})
        return user.is_authenticated and user.id == self.user_id

    async def handle_authenticated_frame(self, frame):
        await self.error("unsupported_type", "Unknown dashboard message", frame)

    async def cleanup_connection(self):
        await self.channel_layer.group_discard(LIVE_DASHBOARD_CHANNEL, self.channel_name)
        if self.user_id is not None:
            await self.channel_layer.group_discard(
                dashboard_channel(self.user_id), self.channel_name)

    async def live_state_changed(self, event):
        await self.send_snapshot()

    async def send_snapshot(self):
        snapshot = registry.snapshot(self.user_id)
        await self.send(text_data=json.dumps({
            "type": "live.state",
            "data": snapshot,
        }, separators=(",", ":")))
