import os
from django.urls import path
from django.core.asgi import get_asgi_application

# # NO IMPORTS BEFORE THIS LINE
# # ============================================================
# # those 2 lines have to be here, in the middle of imports, do not move it elsewhere
# # for more info refer to
# https://stackoverflow.com/questions/53683806/django-apps-arent-loaded-yet-when-using-asgi
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'relay.settings')
django_asgi_app = get_asgi_application()

from .consumers.tally_light import TallyLightConsumer
from .consumers.dashboard import DashboardConsumer
from .consumers.transmitter import TransmitterConsumer
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

application = ProtocolTypeRouter({
    'http': django_asgi_app,

    'websocket': AuthMiddlewareStack(URLRouter([
        path('ws/dashboard', DashboardConsumer.as_asgi()),
        path('ws/lights', TallyLightConsumer.as_asgi()),
        path('ws/transmitters', TransmitterConsumer.as_asgi()),
    ])),
})
