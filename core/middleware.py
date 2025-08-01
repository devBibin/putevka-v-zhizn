from django.shortcuts import redirect
from django.urls import reverse, resolve
from .models import RegistrationAttempt
import logging

logger = logging.getLogger(__name__)

class IncompleteRegistrationRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        path = request.path

        if request.method == 'POST' and request.path.startswith('/check-call-status/'):
            return self.get_response(request)

        resolved = resolve(request.path)
        if resolved.url_name and resolved.url_name.startswith('admin'):
            return self.get_response(request)

        if user.is_authenticated and not user.is_staff and not user.is_superuser:
            if not hasattr(user, '_cached_registration_attempt'):
                try:
                    user._cached_registration_attempt = user.registrationattempt
                except RegistrationAttempt.DoesNotExist:
                    user._cached_registration_attempt = None

            attempt = user._cached_registration_attempt

            if attempt and attempt.current_step != 'finish':
                try:
                    view_name = resolve(request.path_info).view_name
                except:
                    view_name = None

                allowed_views = {
                    'register_initial',
                    'verify_email',
                    'connect_telegram',
                    'verify_phone_if_needed',
                    'wait_for_phone_call',
                    'finish_registration',
                    'redirect_to_current_step',
                    'resend_email_code',
                    'skip_telegram',
                    'logout',
                }

                if view_name not in allowed_views:
                    return redirect(reverse('redirect_to_current_step'))

        return self.get_response(request)


def redirect_to_current_step(request):
    from .views import get_current_registration_attempt
    import logging

    logger = logging.getLogger(__name__)
    logger.debug("Executing redirect_to_current_step view.")

    attempt = get_current_registration_attempt(request)
    if not attempt:
        logger.debug("No current registration attempt found. Redirecting to initial registration.")
        return redirect(reverse('register_initial'))

    step = attempt.current_step
    logger.debug(f"Current registration step: {step}")

    if step == 'email_verification':
        return redirect(reverse('verify_email'))
    elif step == 'telegram_connection':
        return redirect(reverse('connect_telegram'))
    elif step in ['phone_verification_needed', 'wait_for_call']:
        return redirect(reverse('verify_phone_if_needed'))
    elif step == 'finish':
        return redirect(reverse('finish_registration'))

    logger.debug("Unknown step. Redirecting to home.")
    return redirect('/')