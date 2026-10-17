from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_POST

from ..throttling import LoginThrottle


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect("/")
    if request.method == "GET":
        return render(request, "login.html")
    if not LoginThrottle().allow_request(request, login_view):
        return render(request, "login.html", {"error": "Too many attempts. Try again later."},
                      status=429)
    try:
        user = authenticate(request, username=request.POST["name"],
                            password=request.POST["password"])
    except KeyError:
        return render(request, "login.html", {"error": "Name and password are required."},
                      status=400)
    if user is None:
        return render(request, "login.html", {"error": "Incorrect name or password."}, status=401)
    django_login(request, user)
    return HttpResponseRedirect("/")


@require_POST
def logout_view(request):
    django_logout(request)
    return HttpResponseRedirect("/login")
