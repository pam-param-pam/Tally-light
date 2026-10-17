from django.contrib.auth.hashers import check_password

from .models import HardwareCredentials


def token_valid(role, candidate):
    return token_owner(role, candidate) is not None


def token_owner(role, candidate):
    if not isinstance(candidate, str):
        return None
    if role == "transmitter":
        credentials = HardwareCredentials.objects.only("user_id", "transmitter_token_hash")
        for credential in credentials.iterator():
            if check_password(candidate, credential.transmitter_token_hash):
                return credential.user_id
    elif role == "tally_light":
        credentials = HardwareCredentials.objects.only("user_id", "tally_light_token_hash")
        for credential in credentials.iterator():
            if check_password(candidate, credential.tally_light_token_hash):
                return credential.user_id
    return None
