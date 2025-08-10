# app/views_helpers.py
from django.shortcuts import redirect
from django.urls import reverse
import logging

from .decorators import _get_attempt_from_user

logger = logging.getLogger(__name__)

def redirect_to_current_step(request):
    logger.debug("Executing redirect_to_current_step view.")
    attempt = _get_attempt_from_user(request)

    if not attempt:
        logger.debug("No attempt -> register_initial")
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

    logger.debug("Unknown step -> home")
    return redirect('/')
