import asyncio
import json
import logging
from uuid import uuid4

from autobahn.exception import Disconnected
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from ..hardware_auth import token_owner
from ..protocol.frames import FrameType, MAX_FRAME_BYTES


logger = logging.getLogger(__name__)


class AuthenticatedConsumer(AsyncWebsocketConsumer):
    authenticate_on_connect = False
    hello_timeout = 2.5
    ping_interval = 7.5
    pong_timeout = 5
    authentication_interval = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready = False
        self.closing = False
        self.credential_token = None
        self.user_id = None
        self.pending_ping = None
        self.hello_timer = None
        self.ping_timer = None
        self.authentication_timer = None
        self.cleanup_task = None

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._shutdown()

    async def connect(self):
        if self.authenticate_on_connect:
            if not await self.authenticate_connection():
                await self.close(code=4401, reason="Authentication required")
                return
            await self.accept()
            self.ready = True
            await self.after_authentication()
            self._start_background_tasks()
            return
        await self.accept()
        self.hello_timer = asyncio.create_task(self._hello_timeout())

    async def authenticate_connection(self):
        return False

    async def _hello_timeout(self):
        await asyncio.sleep(self.hello_timeout)
        if not self.ready:
            await self.close(code=4408, reason=f"No valid hello received within {self.hello_timeout} seconds")

    async def receive(self, text_data=None, bytes_data=None):
        if self.closing:
            return
        try:
            await self._receive(text_data)
        except asyncio.CancelledError:
            raise
        except KeyError as exc:
            field = str(exc.args[0])
            await self.error("invalid_field", f"Missing required field: {field}", field=field)
        except Exception:
            logger.exception("WebSocket handler failed")
            await self.close(code=1011, reason="Internal WebSocket error")

    async def _receive(self, text_data):
        if text_data is None or len(text_data.encode("utf-8")) > MAX_FRAME_BYTES:
            await self.error("invalid_field", "Expected a JSON text frame below 2 KiB")
            return
        try:
            frame = json.loads(text_data)
        except ValueError:
            await self.error("invalid_field", "Invalid JSON")
            return
        if not isinstance(frame, dict):
            await self.error("invalid_field", "Invalid message envelope")
            return
        if (not isinstance(frame["type"], str)
                or not isinstance(frame["id"], str) or not 1 <= len(frame["id"]) <= 64
                or not isinstance(frame["data"], dict)):
            await self.error("invalid_field", "Invalid message envelope")
            return
        try:
            frame["type"] = FrameType(frame["type"])
        except ValueError:
            await self.error("unsupported_type", "Unknown message type", frame)
            return
        if not self.ready:
            await self._authenticate(frame)
        elif frame["type"] == FrameType.PING:
            await self.send_frame(FrameType.PONG, {}, reply_to=frame["id"],
                                  device_id=self.response_device_id)
        elif frame["type"] == FrameType.PONG:
            if self.pending_ping is None or frame["replyTo"] != self.pending_ping:
                await self.error("invalid_field", "Pong does not match the active ping", frame)
                return
            self.pending_ping = None
        else:
            await self.handle_authenticated_frame(frame)

    async def _authenticate(self, frame):
        if frame["type"] != FrameType.HELLO or not await self.validate_hello(frame):
            return
        token = frame["data"]["token"]
        owner_id = await database_sync_to_async(token_owner)(self.credential_role, token)
        if self.closing:
            return
        if owner_id is None:
            await self.error("unauthorized", f"Invalid {self.credential_name} token", frame)
            await self.close(code=4401, reason=f"Invalid {self.credential_name} token")
            return
        self.user_id = owner_id
        if not await self.register(frame, owner_id) or self.closing:
            return
        self.credential_token = token
        self.user_id = owner_id
        self.ready = True
        self.hello_timer.cancel()
        await self.send_frame(FrameType.WELCOME, {}, reply_to=frame["id"],
                              device_id=self.response_device_id)
        await self.after_authentication(frame)
        self._start_background_tasks()

    def _start_background_tasks(self):
        if self.closing:
            return
        self.ping_timer = asyncio.create_task(self._ping_loop())
        self.authentication_timer = asyncio.create_task(self._authentication_loop())

    async def validate_hello(self, frame):
        if frame["type"] == FrameType.HELLO:
            return True
        await self.error("invalid_field", "Expected hello", frame)
        await self.close(code=4400, reason="Expected hello")
        return False

    async def register(self, frame, owner_id):
        raise NotImplementedError

    async def after_authentication(self, frame=None):
        pass

    async def handle_authenticated_frame(self, frame):
        raise NotImplementedError

    @property
    def response_device_id(self):
        return None

    async def _ping_loop(self):
        try:
            while self.ready:
                await asyncio.sleep(self.ping_interval)
                await self.send_frame(
                    FrameType.PING, {}, device_id=self.response_device_id)
                if not self.ready:
                    return
                await asyncio.sleep(self.pong_timeout)
                if self.pending_ping is not None:
                    await self.close(code=4408, reason="Ping timeout: client did not respond")
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("WebSocket ping failed")
            await self.close(code=1011, reason="WebSocket ping failed")

    async def _authentication_loop(self):
        try:
            while self.ready:
                await asyncio.sleep(self.authentication_interval)
                if not await self.authentication_is_valid():
                    await self.close(code=4401, reason="Authentication is no longer valid")
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("WebSocket authentication revalidation failed")
            await self.close(code=1011, reason="Authentication revalidation failed")

    async def authentication_is_valid(self):
        owner_id = await database_sync_to_async(token_owner)(
            self.credential_role, self.credential_token)
        return owner_id == self.user_id

    async def send_frame(self, message_type: FrameType, data, *, reply_to=None, device_id=None):
        if self.closing:
            return None
        frame_id = uuid4().hex
        if message_type == FrameType.PING:
            self.pending_ping = frame_id
        frame = {"type": message_type, "id": frame_id, "data": data}
        if reply_to is not None:
            frame["replyTo"] = reply_to
        if device_id is not None:
            frame["deviceId"] = device_id
        await self.send(text_data=json.dumps(frame, separators=(",", ":")))
        return frame_id

    async def error(self, code, message, request=None, field=None):
        data = {"code": code, "message": message}
        if field:
            data["field"] = field
        await self.send_frame(FrameType.ERROR, data,
                              reply_to=request["id"] if request else None,
                              device_id=self.response_device_id)

    async def send(self, text_data=None, bytes_data=None, close=False):
        if self.closing:
            return
        try:
            await super().send(text_data=text_data, bytes_data=bytes_data, close=close)
        except (Disconnected, OSError):
            logger.info("WebSocket closing: connection lost while sending")
            await self._shutdown()

    async def close(self, code=None, reason=None):
        if self.closing:
            return
        logger.info("WebSocket closing: %s", reason or "Server requested closure")
        try:
            await self._shutdown()
        finally:
            try:
                await super().close(code=code, reason=reason)
            except (Disconnected, OSError):
                pass

    async def disconnect(self, close_code):
        await self._shutdown()

    async def _shutdown(self):
        self.closing = True
        self.ready = False
        self.pending_ping = None
        for timer in (self.hello_timer, self.ping_timer, self.authentication_timer):
            if timer is not None and timer is not asyncio.current_task():
                timer.cancel()
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self.cleanup_connection())
        await asyncio.shield(self.cleanup_task)

    async def cleanup_connection(self):
        """Remove this connection's live state and channel subscriptions."""
        pass

    async def credentials_rotated(self, event):
        await self.close(code=4401, reason="Hardware credentials were rotated")

    async def authentication_invalidated(self, event):
        await self.close(code=4401, reason="Authentication was invalidated")
