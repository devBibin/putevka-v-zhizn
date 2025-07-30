import logging
import telebot

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect, get_object_or_404

from Putevka import settings
from .forms import CustomUserCreationForm
from .models import TelegramAccount
from .bot import webhook

logger = logging.getLogger(__name__)

_bot_messenger = None


def get_bot_messenger():
    global _bot_messenger
    if _bot_messenger is None:
        if not settings.TG_TOKEN_USERS:
            logger.error("TG_TOKEN_USERS не установлен в settings.py")
            return None
        _bot_messenger = telebot.TeleBot(settings.TG_TOKEN_USERS)
    return _bot_messenger


def index(request):
    return render(request, 'core/index.html')


def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            try:
                telegram_account = TelegramAccount.objects.get(user=user)
            except TelegramAccount.DoesNotExist:
                messages.error(request, "Ошибка: не удалось найти Telegram аккаунт для нового пользователя.")
                logger.error(f"TelegramAccount не найден для пользователя {user.username} после сохранения формы.")
                user.delete()
                return redirect('register')

            telegram_bot_username = get_bot_messenger().get_me().username
            activation_link = (
                f"https://t.me/{telegram_bot_username}?"
                f"start=activate_{telegram_account.activation_token}"
            )

            messages.info(request,
                          f"Спасибо за регистрацию! Пожалуйста, перейдите в Telegram по этой ссылке, "
                          f"нажмите /start и поделитесь своим номером телефона, чтобы завершить активацию: "
                          f"<a href='{activation_link}' target='_blank'>{activation_link}</a>")
            return redirect('registration_pending')
        else:
            messages.error(request, "Ошибка регистрации. Пожалуйста, проверьте введенные данные.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def registration_pending_view(request):
    return render(request, 'registration/pending.html')


def telegram_activate_view(request, token):
    telegram_account = get_object_or_404(TelegramAccount, activation_token=token)
    if telegram_account.is_active_web:
        messages.success(request, "Ваш аккаунт уже активирован!")
        return redirect('login')

    messages.info(request, "Пожалуйста, завершите активацию в Telegram.")
    return redirect('registration_pending')


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
