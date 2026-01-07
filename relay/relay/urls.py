import os

from django.http import HttpResponse, FileResponse
from django.shortcuts import render
from django.urls import path


def index(request):
    return render(request, 'instructions.html')

def download_oldprogram(request):
    file_path = os.path.join('static/old_tallycli.exe')
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='OLD_ATEMlistener.exe')

def download_program(request):
    file_path = os.path.join('static/tallycli.exe')
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='ATEMlistener.exe')

urlpatterns = [
    path("", index, name="index"),
    path("download/program", download_program, name="download a program"),
    path("download/oldprogram", download_oldprogram, name="download a program"),

]
