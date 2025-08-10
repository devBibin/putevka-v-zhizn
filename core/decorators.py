# app/middleware_decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse, resolve
import logging
from .models import RegistrationPersonalData

logger = logging.getLogger(__name__)

STEP_TO_VIEW = {
    'email_verification': 'verify_email',
    'telegram_connection': 'connect_telegram',
    'phone_verification_needed': 'verify_phone_if_needed',
    'wait_for_call': 'verify_phone_if_needed',
    'finish': 'finish_registration',
}
VIEW_TO_STEP = {v: k for k, v in STEP_TO_VIEW.items()}

def _get_current_view_name(request):
    try:
        return resolve(request.path_info).view_name
    except Exception:
        return None

def _should_bypass(request):
    if request.method == 'POST' and request.path.startswith('/check-call-status/'):
        return True
    try:
        r = resolve(request.path)
        if r.url_name and r.url_name.startswith('admin'):
            return True
    except Exception:
        pass
    return False

def _get_attempt_from_user(request):
    if hasattr(request, '_cached_registration_attempt'):
        return request._cached_registration_attempt
    attempt = None
    user = getattr(request, 'user', None)
    if getattr(user, 'is_authenticated', False):
        try:
            attempt = user.registrationpersonaldata
        except RegistrationPersonalData.DoesNotExist:
            attempt = None
    request._cached_registration_attempt = attempt
    return attempt

def ensure_registration_gate(mode: str, *, step: str | None = None):
    """
    mode:
      - 'protected'         → обычные страницы: если регистрация не завершена, редирект на актуальный шаг
      - 'registration_step' → страницы шагов: следим, чтобы юзер был именно на своём шаге
                               (step можно не указывать — определяется по имени вьюхи)
      - 'entry'              → для страницы входа в регистрацию (register_initial):
                               авторизованных с попыткой уводит на их шаг;
                               с finish → на финал; без попытки → пускает на форму.
    """
    if mode not in ('protected', 'registration_step', 'entry'):
        raise ValueError("mode must be 'protected' or 'registration_step'")

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if _should_bypass(request):
                return view_func(request, *args, **kwargs)

            user = request.user
            is_auth = getattr(user, 'is_authenticated', False)

            if is_auth and (user.is_staff or user.is_superuser):
                return view_func(request, *args, **kwargs)

            attempt = _get_attempt_from_user(request)

            if mode == 'protected':
                if is_auth and attempt and attempt.current_step != 'finish':
                    return redirect(reverse('redirect_to_current_step'))
                return view_func(request, *args, **kwargs)

            if mode == 'entry':
                if not is_auth:
                    return view_func(request, *args, **kwargs)

                if attempt:
                    if attempt.current_step == 'finish':
                        return redirect(reverse('finish_registration'))
                    return redirect(reverse('redirect_to_current_step'))

                return view_func(request, *args, **kwargs)

            if not attempt:
                return redirect(reverse('register_initial'))

            current_view = _get_current_view_name(request)
            expected_view = STEP_TO_VIEW.get(attempt.current_step)

            if attempt.current_step == 'finish' and current_view != 'finish_registration':
                return redirect(reverse('finish_registration'))

            if expected_view and current_view != expected_view:
                return redirect(reverse(expected_view))

            return view_func(request, *args, **kwargs)

        return _wrapped
    return decorator
