from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..services.errors import ServiceError
from ..services.tally_lights import TallyLightService
from ..throttling import DashboardThrottle
from .serializers import (ConnectedTallyLightSerializer, LiveSnapshotSerializer,
                          SettingsUpdateSerializer, SettingsUpdatesSerializer)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DashboardThrottle])
def tally_light_list(request):
    tally_lights = ConnectedTallyLightSerializer.serialize_many(
        TallyLightService.connected_tally_lights(request.user.id))
    return Response({"tally_lights": tally_lights})


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DashboardThrottle])
def all_tally_light_settings(request):
    try:
        result = TallyLightService.update_all_brightness(request.user.id, request.data["brightness"])
    except (KeyError, TypeError):
        return Response({"error": "Missing field: brightness", "field": "brightness"}, status=400)
    except ServiceError as exc:
        payload = {"error": str(exc)}
        if exc.field is not None:
            payload["field"] = exc.field
            return Response(payload, status=400)
        return Response(payload, status=409)
    return Response(SettingsUpdatesSerializer.serialize(result), status=202)


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DashboardThrottle])
def tally_light_settings(request, device_id):
    try:
        result = TallyLightService.update_tally_light_settings(request.user.id, device_id, request.data)
    except ServiceError as exc:
        payload = {"error": str(exc)}
        if exc.field is not None:
            payload["field"] = exc.field
            return Response(payload, status=400)
        return Response(payload, status=409)
    return Response(SettingsUpdateSerializer.serialize(result), status=202)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DashboardThrottle])
def live(request):
    return Response(LiveSnapshotSerializer.serialize(TallyLightService.live_snapshot(request.user.id)))
