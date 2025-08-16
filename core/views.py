import logging
import random
import uuid
from datetime import timezone

import requests

import telebot

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import config
from Putevka import settings
from .decorators import ensure_registration_gate
from .forms import CustomUserCreationForm, RegistrationForm, VerifyEmailForm, PhoneNumberForm
from .models import TelegramAccount, RegistrationPersonalData, UserInfo
from .bot import webhook
from .services.email_service import _send_email_verification_code
from .services.zvonok_service import initiate_zvonok_verification, _poll_zvonok_status
from django.db import transaction

logger = logging.getLogger(__name__)

_bot_messenger = None


@ensure_registration_gate('protected')
def index(request):
    return render(request, 'core/index.html')


@ensure_registration_gate('entry')
def register_initial(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            if User.objects.filter(email=email, is_active=True).exists():
                form.add_error('email', 'Пользователь с таким email уже зарегистрирован.')
            else:
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    is_active=True,
                )
                telegram_account = TelegramAccount.objects.create(
                    user=user,
                    activation_token=uuid.uuid4()
                )
                user_info = UserInfo.objects.create(user=user)

                new_attempt = RegistrationPersonalData.objects.create(
                    user=user,
                    telegram_account=telegram_account,
                    email=email,
                    password=user.password,
                    current_step='email_verification',
                    token=uuid.uuid4()
                )
                new_attempt.generate_email_code()
                _send_email_verification_code(new_attempt)
                login(request, user)
                return redirect(reverse('verify_email'))
    else:
        form = RegistrationForm()

    return render(request, 'registration/register_initial.html', {'form': form})


@ensure_registration_gate('registration_step')
def verify_email(request):
    attempt = request.user.registrationpersonaldata

    email_code_expired = attempt.is_email_code_expired() or not attempt.email_verification_code

    if request.method == 'POST':
        form = VerifyEmailForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            if not email_code_expired and code == attempt.email_verification_code:
                attempt.email_verified = True
                attempt.current_step = 'telegram_connection'
                attempt.save(update_fields=['email_verified', 'current_step'])
                return redirect(reverse('connect_telegram'))
            form.add_error('code', 'Неверный или истекший код. Пожалуйста, попробуйте снова или запросите новый.')
    else:
        form = VerifyEmailForm()

    return render(request, 'registration/verify_email.html', {
        'form': form,
        'email': attempt.email,
        'email_code_expired': email_code_expired,
    })

@require_POST
@ensure_registration_gate('registration_step')
def resend_email_code(request):
    attempt = request.user.registrationpersonaldata

    attempt.generate_email_code()
    if hasattr(attempt, 'email_code_sent_at'):
        attempt.email_code_sent_at = timezone.now()
        attempt.save(update_fields=['email_verification_code', 'email_code_expires_at', 'email_code_sent_at'])
    else:
        attempt.save(update_fields=['email_verification_code', 'email_code_expires_at'])

    _send_email_verification_code(attempt)
    return redirect(reverse('verify_email'))


@ensure_registration_gate('registration_step')
def connect_telegram(request):
    attempt = request.user.registrationpersonaldata

    bot_username = config.TG_BOT_USERS_USERNAME
    activation_token = attempt.telegram_account.activation_token
    telegram_bot_link = f"https://t.me/{bot_username}?start=activate_{activation_token}"

    if request.method == 'POST':
        attempt.telegram_account.refresh_from_db()

        if attempt.telegram_account.telegram_verified:
            attempt.current_step = 'finish'
            attempt.save(update_fields=['current_step'])
            return redirect(reverse('finish_registration'))

        return render(request, 'registration/connect_telegram.html', {
            'telegram_bot_link': telegram_bot_link,
            'is_telegram_account_active_web': False,
            'error_message': 'Пожалуйста, сначала нажмите Start у бота и дождитесь привязки аккаунта.'
        })

    is_verified = attempt.telegram_account.telegram_verified
    return render(request, 'registration/connect_telegram.html', {
        'telegram_bot_link': telegram_bot_link,
        'is_telegram_account_active_web': is_verified
    })


def skip_telegram(request):
    attempt = request.user.registrationpersonaldata
    if not attempt.email_verified:
        return redirect(reverse('register_initial'))

    attempt.current_step = 'phone_verification_needed'
    attempt.save()
    return redirect(reverse('verify_phone_if_needed'))


@ensure_registration_gate('registration_step')
def verify_phone_if_needed(request):
    attempt = request.user.registrationpersonaldata

    if attempt.current_step == 'wait_for_call':
        return redirect(reverse('wait_for_phone_call'))

    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
        if form.is_valid():
            print("CLEANED:", form.cleaned_data)
            phone_number = form.cleaned_data['phone_number']
            pincode = f"{random.randint(1000, 9999)}"

            api_resp = initiate_zvonok_verification(phone_number, pincode=pincode)
            ok = False
            err_msg = None
            if isinstance(api_resp, dict):
                ok = api_resp.get('ok', bool(api_resp))
                err_msg = api_resp.get('message')
            else:
                ok = bool(api_resp)

            if ok:
                print(phone_number)
                attempt.phone_number = phone_number
                attempt.current_step = 'wait_for_call'
                attempt.save(update_fields=['phone_number', 'current_step'])

                user_info = request.user.user_info
                if user_info:
                    user_info.phone_number = phone_number
                    user_info.save(update_fields=['phone_number'])

                return redirect(reverse('wait_for_phone_call'))

            form.add_error(None, err_msg or 'Не удалось инициировать проверку звонком. Попробуйте ещё раз.')
    else:
        form = PhoneNumberForm()

    return render(request, 'registration/enter_phone_number.html', {'form': form})


def wait_for_phone_call(request):
    attempt = request.user.registrationpersonaldata
    return render(request, 'registration/wait_for_phone_call.html', {
        'phone_number': attempt.phone_number,
    })


def check_phone_call_status(request):
    attempt = request.user.registrationpersonaldata

    if not attempt or not attempt.phone_number:
        return JsonResponse({'status': 'error', 'message': 'Незавершенная регистрация не найдена.'}, status=400)

    api_resp = _poll_zvonok_status(attempt.phone_number)
    if api_resp is None or api_resp is False:
        return JsonResponse({'status': 'error', 'message': 'Ошибка API zvonok.com.'}, status=502)

    dial_status = None
    if isinstance(api_resp, dict):
        dial_status = api_resp.get('dial_status_display')

    SUCCESS_STATUSES = {'Абонент ответил'}
    if dial_status in SUCCESS_STATUSES:
        with transaction.atomic():
            attempt.phone_verified = True
            attempt.current_step = 'finish'
            attempt.save(update_fields=['phone_verified', 'current_step'])

            user = attempt.user
            if user and not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

            tg = attempt.telegram_account
            if tg and not tg.telegram_verified:
                tg.telegram_verified = True
                tg.activation_token = None
                tg.save(update_fields=['telegram_verified', 'activation_token'])

        return JsonResponse({'status': 'success', 'message': 'Номер телефона успешно подтвержден!'})

    return JsonResponse({
        'status': 'pending',
        'message': 'Ожидание звонка...',
        'dial_status': dial_status
    })


def change_phone_number(request):
    attempt = request.user.registrationpersonaldata
    attempt.phone_number = None
    attempt.current_step = 'phone_verification_needed'
    attempt.save(update_fields=['phone_number', 'current_step'])
    return redirect(reverse('verify_phone_if_needed'))

def return_to_telegram_connection(request):
    attempt = request.user.registrationpersonaldata
    attempt.current_step = 'telegram_connection'
    attempt.save(update_fields=['current_step'])
    return redirect(reverse('connect_telegram'))

@ensure_registration_gate('registration_step')
def finish_registration(request):
    attempt = request.user.registrationpersonaldata

    user = attempt.user
    if user and not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active'])

    login(request, user)

    return render(request, 'registration/registration_complete.html', {'user': user})


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
