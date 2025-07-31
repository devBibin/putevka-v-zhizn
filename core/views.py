import logging
import random
import uuid
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

from Putevka import settings
from .forms import CustomUserCreationForm, RegistrationForm, VerifyEmailForm, PhoneNumberForm
from .models import TelegramAccount, RegistrationAttempt
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


def _send_email_verification_code(attempt):
    subject = 'Ваш код подтверждения регистрации'
    message = f'Привет!\n\nВаш код подтверждения для регистрации: {attempt.email_verification_code}\n\n' \
              f'Этот код действителен в течение 15 минут. Если вы не запрашивали этот код, просто проигнорируйте это письмо.'
    email_from = settings.DEFAULT_FROM_EMAIL
    recipient_list = [attempt.email]
    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        print(f"DEBUG: Отправлен email на {attempt.email} с кодом: {attempt.email_verification_code}")
        return True
    except Exception as e:
        print(f"ERROR: Не удалось отправить email на {attempt.email}: {e}")
        return False


def _initiate_zvonok_verification(phone_number, pincode=None):
    url = settings.ZVONOK_API_INITIATE_URL
    data = {
        'public_key': settings.PUBLIC_KEY_CALL,
        'phone': phone_number,
        'campaign_id': settings.CAMPAIGN_ID,
    }
    if pincode:
        data['pincode'] = pincode

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP-ошибка при вызове API zvonok.com (initiate): {e.response.status_code} - {e.response.text}")
        return {
            "status": "error",
            "message": f"Ошибка сервиса звонков: {e.response.status_code}. Пожалуйста, попробуйте позже."
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения при вызове API zvonok.com (initiate): {e}")
        return {
            "status": "error",
            "message": "Не удалось подключиться к сервису звонков. Пожалуйста, проверьте интернет-соединение или попробуйте позже."
        }
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в _initiate_zvonok_verification: {e}")
        return {
            "status": "error",
            "message": "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        }

def _poll_zvonok_status(phone_number):
    url = settings.ZVONOK_API_POLLING_URL
    params = {
        'public_key': settings.PUBLIC_KEY_CALL,
        'phone': phone_number,
        'campaign_id': settings.CAMPAIGN_ID
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json() if (isinstance(response.json(), dict)) else response.json()[0]
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при вызове API zvonok.com (polling): {e}")
        return None

def get_current_registration_attempt(request):
    token_str = request.session.get('registration_attempt_token')
    if token_str:
        try:
            return RegistrationAttempt.objects.get(token=uuid.UUID(token_str))
        except (RegistrationAttempt.DoesNotExist, ValueError):
            del request.session['registration_attempt_token']
    return None


def register_initial(request):
    if request.user.is_authenticated:
        return redirect('/')

    attempt = get_current_registration_attempt(request)

    if attempt:
        if not attempt.email_verified:
            return redirect(reverse('verify_email'))
        elif attempt.telegram_account and not attempt.telegram_account.is_active_web and not attempt.phone_verified:
            return redirect(reverse('connect_telegram'))
        elif not attempt.phone_verified and attempt.current_step in ['phone_verification_needed', 'wait_for_call']:
            return redirect(reverse('wait_for_phone_call'))  # Перенаправляем на страницу ожидания
        elif attempt.current_step == 'finish':
            return redirect(reverse('finish_registration'))
        return redirect('login')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            if User.objects.filter(email=email, is_active=True).exists():
                form.add_error('email', 'Пользователь с таким email уже зарегистрирован.')
            else:
                existing_attempt = RegistrationAttempt.objects.filter(email=email).first()
                if existing_attempt:
                    if not existing_attempt.email_verified:
                        existing_attempt.generate_email_code() # Генерируем новый код
                        _send_email_verification_code(existing_attempt)
                        request.session['registration_attempt_token'] = str(existing_attempt.token)
                        return redirect(reverse('verify_email'))
                    elif existing_attempt.telegram_account and not existing_attempt.telegram_account.telegram_verified and not existing_attempt.phone_verified:
                        request.session['registration_attempt_token'] = str(existing_attempt.token)
                        return redirect(reverse('connect_telegram'))
                    else:
                        form.add_error('email', 'Пользователь с таким email уже существует или находится в процессе завершения регистрации.')
                else:
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=make_password(password),
                        is_active=False
                    )
                    telegram_account = TelegramAccount.objects.create(
                        user=user,
                        activation_token=uuid.uuid4()
                    )

                    new_attempt = RegistrationAttempt.objects.create(
                        user=user,
                        telegram_account=telegram_account,
                        email=email,
                        password=user.password,
                        current_step='email_verification',
                        token=uuid.uuid4()
                    )
                    new_attempt.generate_email_code()
                    _send_email_verification_code(new_attempt)
                    request.session['registration_attempt_token'] = str(new_attempt.token)
                    return redirect(reverse('verify_email'))
        else:
            pass
    else:
        form = RegistrationForm()

    return render(request, 'registration/register_initial.html', {'form': form})


def verify_email(request):
    attempt = get_current_registration_attempt(request)
    if not attempt:
        return redirect(reverse('register_initial'))

    if attempt.email_verified:
        return redirect(reverse('connect_telegram'))

    if request.method == 'POST':
        form = VerifyEmailForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            if code == attempt.email_verification_code and not attempt.is_email_code_expired():
                attempt.email_verified = True
                attempt.current_step = 'telegram_connection'
                attempt.save()
                return redirect(reverse('connect_telegram'))
            else:
                form.add_error('code', 'Неверный или истекший код. Пожалуйста, попробуйте снова или запросите новый.')
    else:
        form = VerifyEmailForm()

    if attempt.is_email_code_expired() or not attempt.email_verification_code:
        request.session['email_code_expired'] = True
    else:
        request.session['email_code_expired'] = False

    return render(request, 'registration/verify_email.html', {
        'form': form,
        'email': attempt.email,
        'email_code_expired': request.session.get('email_code_expired', False)
    })


def resend_email_code(request):
    attempt = get_current_registration_attempt(request)
    if not attempt or attempt.email_verified:
        return redirect(reverse('register_initial'))

    attempt.generate_email_code()
    _send_email_verification_code(attempt)
    request.session['email_code_expired'] = False
    return redirect(reverse('verify_email'))


def connect_telegram(request):
    attempt = get_current_registration_attempt(request)
    if not attempt:
        return redirect(reverse('register_initial'))

    if not attempt.email_verified:
        return redirect(reverse('verify_email'))

    if attempt.telegram_account and attempt.telegram_account.telegram_verified:
        attempt.current_step = 'finish'
        attempt.save()
        return redirect(reverse('finish_registration'))

    telegram_bot_link = f"https://t.me/{settings.TG_BOT_USERS_USERNAME}?start=activate_{attempt.telegram_account.activation_token}"

    if request.method == 'POST':
        attempt.telegram_account.refresh_from_db()
        if attempt.telegram_account.telegram_verified:
            attempt.current_step = 'finish'
            attempt.save()
            return redirect(reverse('finish_registration'))
        else:
            return render(request, 'registration/connect_telegram.html', {
                'telegram_bot_link': telegram_bot_link,
                'error_message': 'Пожалуйста, сначала взаимодействуйте с ботом и убедитесь, что он привязал ваш аккаунт и активировал веб-доступ.'
            })

    return render(request, 'registration/connect_telegram.html', {
        'telegram_bot_link': telegram_bot_link,
        'is_telegram_account_active_web': attempt.telegram_account and attempt.telegram_account.telegram_verified
    })


def skip_telegram(request):
    attempt = get_current_registration_attempt(request)
    if not attempt or not attempt.email_verified:
        return redirect(reverse('register_initial'))

    attempt.current_step = 'phone_verification_needed'
    attempt.save()
    return redirect(reverse('verify_phone_if_needed'))


def verify_phone_if_needed(request):
    attempt = get_current_registration_attempt(request)
    if not attempt:
        return redirect(reverse('register_initial'))

    if not attempt.email_verified:
        return redirect(reverse('verify_email'))

    if attempt.user and attempt.user.is_active:
        return redirect(reverse('finish_registration'))

    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']

            pincode = str(random.randint(1000, 9999))

            api_response = _initiate_zvonok_verification(phone_number, pincode=pincode)

            if api_response:
                attempt.phone_number = phone_number
                attempt.phone_verification_code = pincode
                attempt.current_step = 'wait_for_call'
                attempt.save()

                return redirect(reverse('wait_for_phone_call'))
            else:
                error_message = api_response.get('message', 'Произошла ошибка при инициации проверки звонка.')
                form.add_error(None, error_message)
    else:
        form = PhoneNumberForm()

    return render(request, 'registration/enter_phone_number.html', {'form': form})

def wait_for_phone_call(request):
    attempt = get_current_registration_attempt(request)
    if not attempt or not attempt.email_verified or not attempt.phone_number or attempt.phone_verified:
        return redirect(reverse('register_initial'))

    return render(request, 'registration/wait_for_phone_call.html', {
        'phone_number': attempt.phone_number,
    })


@csrf_exempt
def check_phone_call_status(request):
    if request.method == 'POST':
        attempt = get_current_registration_attempt(request)
        if not attempt or not attempt.phone_number:
            return JsonResponse({'status': 'error', 'message': 'Незавершенная регистрация не найдена.'})

        api_response = _poll_zvonok_status(attempt.phone_number)

        if api_response:
            is_call_successful = False
            dial_status = api_response.get("dial_status_display")

            if dial_status == 'Абонент ответил':
                is_call_successful = True

            if is_call_successful:
                attempt.phone_verified = True
                if attempt.user and not attempt.user.is_active:
                    attempt.user.is_active = True
                    attempt.user.save()
                    if attempt.telegram_account and not attempt.telegram_account.telegram_verified:
                        attempt.telegram_account.is_active_web = True
                        attempt.telegram_account.activation_token = None
                        attempt.telegram_account.save()

                attempt.current_step = 'finish'
                attempt.save()
                return JsonResponse({'status': 'success', 'message': 'Номер телефона успешно подтвержден!'})

            return JsonResponse({'status': 'pending', 'message': 'Ожидание звонка...'})

        return JsonResponse({'status': 'error', 'message': 'Ошибка API zvonok.com.'})

    return JsonResponse({'status': 'error', 'message': 'Доступен только POST-запрос.'}, status=405)


def finish_registration(request):
    attempt = get_current_registration_attempt(request)
    if not attempt:
        return redirect(reverse('register_initial'))

    if not attempt.email_verified:
        return redirect(reverse('verify_email'))

    if not attempt.user or not attempt.user.is_active:
        return redirect(reverse('connect_telegram'))

    login(request, attempt.user)
    request.session.pop('registration_attempt_token', None)
    return render(request, 'registration/registration_complete.html', {'user': attempt.user})


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
