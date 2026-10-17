from django.conf import settings
from django.db import models


class HardwareCredentials(models.Model):
    """One hardware credential set owned by one dashboard user."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="hardware_credentials")
    transmitter_token_hash = models.CharField(max_length=256)
    tally_light_token_hash = models.CharField(max_length=256)
    rotated_at = models.DateTimeField(auto_now=True)
