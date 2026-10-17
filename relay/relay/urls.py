from django.urls import path

from .api.tally_lights import live as live_api
from .api.tally_lights import (all_tally_light_settings, tally_light_list,
                               tally_light_settings)
from .api.relay import relay_check
from .pages.account import account
from .pages.authentication import login_view, logout_view
from .pages.dashboard import colors, faq, index, live


urlpatterns = [
    path("", index, name="index"),
    path("login", login_view, name="login"),
    path("logout", logout_view, name="logout"),
    path("account", account, name="account"),
    path("live", live, name="live"),
    path("colors", colors, name="colors"),
    path("faq", faq, name="faq"),
    path("api/relay/check", relay_check, name="relay_check"),
    path("api/tally-lights", tally_light_list, name="tally_light_list"),
    path("api/tally-lights/settings", all_tally_light_settings, name="all_tally_light_settings"),
    path("api/tally-lights/<str:device_id>/settings", tally_light_settings, name="tally_light_settings"),
    path("api/live", live_api, name="live_api"),
]
