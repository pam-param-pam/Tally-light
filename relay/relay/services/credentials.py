import secrets
from urllib.parse import urlsplit, urlunsplit

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.hashers import make_password

from ..live_state import registry
from ..models import HardwareCredentials
from .errors import ServiceError


class HardwareCredentialService:
    @staticmethod
    def credentials_for(user):
        return HardwareCredentials.objects.filter(user=user).first()

    @staticmethod
    def normalize_relay_url(value):
        if not isinstance(value, str) or value != value.strip():
            raise ServiceError("Enter a valid public relay URL.")
        parts = urlsplit(value)
        scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}.get(parts.scheme)
        if (not scheme or not parts.hostname or parts.username or parts.password or parts.query
                or parts.fragment or parts.path not in ("", "/", "/ws/lights", "/ws/transmitters")):
            raise ServiceError("Enter a valid public relay URL.")
        try:
            port = parts.port
        except ValueError:
            raise ServiceError("Enter a valid public relay URL.") from None
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        authority = host + (f":{port}" if port is not None else "")
        return urlunsplit((scheme, authority, "/ws/lights", "", ""))

    @classmethod
    def generate(cls, user, relay_url, current_password, *, rotate=False, confirmed=False):
        existing = cls.credentials_for(user)
        if rotate != (existing is not None):
            raise ServiceError("Hardware credential state changed. Reload this page and try again.")
        if rotate and not confirmed:
            raise ServiceError("Confirm that you want to revoke both current tokens.")
        if not user.check_password(current_password or ""):
            raise ServiceError("Your current password is incorrect.")
        relay_url = cls.normalize_relay_url(relay_url)
        transmitter_token = secrets.token_urlsafe(32)
        tally_light_token = secrets.token_urlsafe(32)
        token_hashes = {
            "transmitter_token_hash": make_password(transmitter_token),
            "tally_light_token_hash": make_password(tally_light_token),
        }
        if existing is None:
            HardwareCredentials.objects.create(user=user, **token_hashes)
        else:
            existing.transmitter_token_hash = token_hashes["transmitter_token_hash"]
            existing.tally_light_token_hash = token_hashes["tally_light_token_hash"]
            existing.save(update_fields=["transmitter_token_hash", "tally_light_token_hash", "rotated_at"])
        if rotate:
            layer = get_channel_layer()
            for channel in registry.hardware_channels(user.pk):
                async_to_sync(layer.send)(channel, {"type": "credentials_rotated"})
        return {"relay_url": relay_url, "transmitter_token": transmitter_token,
                "tally_light_token": tally_light_token}
