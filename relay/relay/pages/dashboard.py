from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def index(request):
    return render(request, "landing.html")


@login_required
def live(request):
    return render(request, "live.html")


@login_required
def colors(request):
    return render(request, "colors.html")


@login_required
def faq(request):
    return render(request, "faq.html")
