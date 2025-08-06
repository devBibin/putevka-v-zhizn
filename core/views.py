from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib import messages
from telegram_bot_polling import bot
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.http import HttpResponse

from telegram_bot_polling import bot

def index(request):
    return render(request, 'core/index.html')


def register(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('index')

        User.objects.create_user(username=username, password=password)
        messages.success(request, "Registration successful. You can now log in.")
        return redirect('index')

    return redirect('index')



def login_view(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome, {user.username}!")
            return redirect('index')
        else:
            messages.error(request, "Invalid credentials")
            return redirect('index')

    return redirect('index')

@csrf_exempt
def telegram_webhook(request):
    if request.method == "POST":
        try:
            json_data = json.loads(request.body)
            bot.process_new_updates([json_data])
            return JsonResponse({"ok": True})
        except Exception as e:
            # Логируем ошибку, если нужно
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
    else:
        return JsonResponse({"ok": False}, status=400)

def home_view(request):
    return HttpResponse("Добро пожаловать на главную страницу!")