import logging

from django.core.mail import send_mail
from django.urls import reverse

import config
from Putevka import settings

logger = logging.getLogger(__name__)


def send_email_verification_code(attempt):
    confirm_path = reverse('verify_email_confirm', kwargs={'token': attempt.email_verification_code})
    confirm_url = f"{config.BASE_URL}{confirm_path}"

    subject = 'Ваш код подтверждения регистрации'
    message = f'Привет!\n\nВаша ссылка для подтверждения регистрации: {confirm_url}\n\n' \
              f'Этот код действителен в течение 15 минут. Если вы не запрашивали этот код, просто проигнорируйте это письмо.'
    email_from = settings.DEFAULT_FROM_EMAIL
    recipient_list = [attempt.email]
    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        logger.info(f"Отправлен email на {attempt.email} с кодом: {attempt.email_verification_code} для {attempt.user}")
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить email на {attempt.email}: {e}, для {attempt.user}")
        return False
