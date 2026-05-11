import logging

from django.core.mail import EmailMultiAlternatives, send_mail
from django.urls import reverse

import config
from Putevka import settings

logger = logging.getLogger(__name__)


def send_email_message(
    subject: str,
    to: list[str],
    text: str,
    html: str | None = None,
) -> None:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not from_email:
        logger.warning("DEFAULT_FROM_EMAIL не задан, email не отправлен")
        return

    if not to:
        logger.warning("Список получателей пуст, email не отправлен")
        return

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email,
        to=to,
    )
    if html:
        msg.attach_alternative(html, "text/html")
    msg.send()

    logger.info("Сообщение отправлено на почту: %s", ", ".join(to))


def get_email_verification_link(attempt):
    confirm_path = reverse("verify_email_confirm", kwargs={"token": attempt.email_verification_code})
    confirm_url = f"{config.BASE_URL}{confirm_path}"
    return confirm_url


def send_email_verification_code(attempt):
    confirm_url = get_email_verification_link(attempt)

    subject = "Ваш код подтверждения регистрации"
    message = (
        "Привет!\n\n"
        f"Ваша ссылка для подтверждения регистрации: {confirm_url}\n\n"
        "Этот код действителен в течение 15 минут. "
        "Если вы не запрашивали этот код, просто проигнорируйте это письмо."
    )
    email_from = settings.DEFAULT_FROM_EMAIL
    recipient_list = [attempt.email]
    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        logger.info(
            "Отправлен email на %s с кодом %s для %s",
            attempt.email,
            attempt.email_verification_code,
            attempt.user,
        )
        return True
    except Exception as e:
        logger.error(
            "Не удалось отправить email на %s: %s, для %s",
            attempt.email,
            e,
            attempt.user,
        )
        return False


def send_email_to_user(subject: str, user, text: str, html: str | None = None) -> None:
    email = user.username
    if not email:
        return

    try:
        send_email_message(subject=subject, to=[email], text=text, html=html)
        logger.info("Сообщение отправлено пользователю на почту %s", email)
    except Exception as e:
        logger.warning("Ошибка при отправке email пользователю %s: %s", user, e)
