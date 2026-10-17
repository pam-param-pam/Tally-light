from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ..live_state import dashboard_channel
from .errors import ServiceError


class AccountService:
    @staticmethod
    def change_username(user, username, current_password):
        if not user.check_password(current_password or ""):
            raise ServiceError("Your current password is incorrect.")
        try:
            username = user._meta.get_field("username").clean(username, user)
        except ValidationError as exc:
            raise ServiceError(" ".join(exc.messages)) from exc
        if type(user)._default_manager.filter(username=username).exclude(pk=user.pk).exists():
            raise ServiceError("A user with that username already exists.")
        user.username = username
        user.save(update_fields=["username"])

    @staticmethod
    def change_password(user, old_password, new_password, confirmation):
        if not user.check_password(old_password or ""):
            raise ServiceError("Your current password is incorrect.")
        if new_password != confirmation:
            raise ServiceError("The new passwords do not match.")
        try:
            password_validation.validate_password(new_password, user)
        except ValidationError as exc:
            raise ServiceError(" ".join(exc.messages)) from exc
        user.set_password(new_password)
        user.save(update_fields=["password"])
        async_to_sync(get_channel_layer().group_send)(
            dashboard_channel(user.pk), {"type": "authentication_invalidated"})
        return user
