from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..hardware_auth import token_valid
from ..throttling import RelayAuthThrottle


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([RelayAuthThrottle])
def relay_check(request):
    try:
        token = request.data["token"]
    except (KeyError, TypeError):
        return Response({"error": "Missing transmitter token."}, status=400)
    if not token_valid("transmitter", token):
        return Response({"error": "Invalid transmitter token"}, status=401)
    return Response({"ok": True})
