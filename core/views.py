import logging
import uuid

import telebot

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from Putevka import settings
from .forms import CustomUserCreationForm, RegistrationForm, VerifyEmailForm, VerifyPhoneForm, PhoneNumberForm
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


def _make_phone_call_verification(attempt):
    print(f"DEBUG: Имитация звонка на номер {attempt.phone_number}. Код: {attempt.phone_verification_code}")
    return True

def get_current_registration_attempt(request):
    token_str = request.session.get('registration_attempt_token')
    if token_str:
        try:
            return RegistrationAttempt.objects.get(token=uuid.UUID(token_str))
        except (RegistrationAttempt.DoesNotExist, ValueError):
            del request.session['registration_attempt_token']
    return None


def register_initial(request):
    attempt = get_current_registration_attempt(request)

    if attempt:
        if not attempt.email_verified:
            return redirect(reverse('verify_email'))
        elif attempt.telegram_account and not attempt.telegram_account.telegram_verified and not attempt.phone_verified:
            return redirect(reverse('connect_telegram'))
        elif attempt.current_step == 'phone_verification_needed':
            return redirect(reverse('verify_phone_if_needed'))
        elif attempt.current_step == 'phone_verification_code':
            return redirect(reverse('verify_phone_code'))
        elif attempt.current_step == 'finish':
            return redirect(reverse('finish_registration'))
        return redirect(reverse('login'))

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
            attempt.phone_number = phone_number
            attempt.generate_phone_code()
            attempt.current_step = 'phone_verification_code'
            attempt.save()
            _make_phone_call_verification(attempt)
            return redirect(reverse('verify_phone_code'))
    else:
        initial_phone = None
        if attempt.telegram_account and attempt.telegram_account.telegram_id and not attempt.telegram_account.telegram_verified:
            initial_phone = attempt.phone_number

        form = PhoneNumberForm(initial={'phone_number': initial_phone})

    return render(request, 'registration/enter_phone_number.html', {
        'form': form,
        'is_telegram_account_active_web': attempt.telegram_account and attempt.telegram_account.telegram_verified
    })


def verify_phone_code(request):
    attempt = get_current_registration_attempt(request)
    if not attempt:
        return redirect(reverse('register_initial'))

    if not attempt.email_verified:
        return redirect(reverse('verify_email'))

    if attempt.user and attempt.user.is_active:
        return redirect(reverse('finish_registration'))

    if not attempt.phone_number:
        return redirect(reverse('verify_phone_if_needed'))

    if request.method == 'POST':
        form = VerifyPhoneForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            if code == attempt.phone_verification_code and not attempt.is_phone_code_expired():
                attempt.phone_verified = True
                if attempt.user and not attempt.user.is_active:
                    attempt.user.is_active = True
                    attempt.user.save()
                    if attempt.telegram_account and not attempt.telegram_account.telegram_verified:
                        attempt.telegram_account.telegram_verified = True
                        attempt.telegram_account.activation_token = None  # Обнуляем токен
                        attempt.telegram_account.save()

                attempt.current_step = 'finish'
                attempt.save()
                return redirect(reverse('finish_registration'))
            else:
                form.add_error('code', 'Неверный или истекший код. Пожалуйста, попробуйте снова или запросите новый.')
    else:
        form = VerifyPhoneForm()

    if attempt.is_phone_code_expired() or not attempt.phone_verification_code:
        request.session['phone_code_expired'] = True  # Флаг для шаблона
    else:
        request.session['phone_code_expired'] = False

    return render(request, 'registration/verify_phone_code.html', {
        'form': form,
        'phone_number': attempt.phone_number,
        'phone_code_expired': request.session.get('phone_code_expired', False)
    })


def resend_phone_code(request):
    attempt = get_current_registration_attempt(request)
    if not attempt or attempt.phone_verified or not attempt.phone_number:
        return redirect(reverse('register_initial'))

    attempt.generate_phone_code()
    _make_phone_call_verification(attempt)
    request.session['phone_code_expired'] = False
    return redirect(reverse('verify_phone_code'))


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
