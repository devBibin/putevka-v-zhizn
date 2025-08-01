import logging

from django.core.mail import send_mail

from Putevka import settings

logger = logging.getLogger(__name__)


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
