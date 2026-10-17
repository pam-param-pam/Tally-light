import json

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..services.account import AccountService
from ..services.credentials import HardwareCredentialService
from ..services.errors import ServiceError


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    hardware_credentials = HardwareCredentialService.credentials_for(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "username":
                AccountService.change_username(
                    request.user, request.POST.get("username", ""),
                    request.POST.get("current_password", ""))
                messages.success(request, "Your username has been updated.")
                return redirect("account")
            if action == "password":
                user = AccountService.change_password(
                    request.user, request.POST.get("old_password", ""),
                    request.POST.get("new_password1", ""), request.POST.get("new_password2", ""))
                update_session_auth_hash(request, user)
                messages.success(request, "Your password has been updated.")
                return redirect("account")
            if action in ("generate_hardware_credentials", "rotate_hardware_credentials"):
                payload = HardwareCredentialService.generate(
                    request.user, request.POST.get("relay_url", ""),
                    request.POST.get("current_password", ""),
                    rotate=action == "rotate_hardware_credentials",
                    confirmed=request.POST.get("confirm_rotation") == "yes")
                response = HttpResponse(json.dumps(payload, indent=2) + "\n",
                                        content_type="application/json")
                response["Content-Disposition"] = 'attachment; filename="Tally-Connection-Profile.json"'
                response["Cache-Control"] = "no-store"
                return response
        except ServiceError as exc:
            messages.error(request, str(exc))
    return render(request, "account.html", {
        "hardware_credentials": hardware_credentials,
        "username_value": request.POST.get("username", request.user.username),
        "suggested_relay_url": HardwareCredentialService.normalize_relay_url(
            request.build_absolute_uri("/")),
    })
