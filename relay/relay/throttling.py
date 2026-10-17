from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class IPRateThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(IPRateThrottle):
    scope = "login"


class RelayAuthThrottle(IPRateThrottle):
    scope = "relay_auth"


class DashboardThrottle(UserRateThrottle):
    scope = "dashboard"
