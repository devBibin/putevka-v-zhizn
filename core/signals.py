import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from telebot import TeleBot

import config
from core.bot import send_tg_notification_to_user
from core.models import MotivationLetter

TELEGRAM_STAFF_CHAT_IDS = config.TELEGRAM_STAFF_CHAT_IDS
TG_TOKEN = config.TG_TOKEN_ADMIN
bot = TeleBot(TG_TOKEN)

import config as app_config

TELEGRAM_CHAT_IDS = app_config.TELEGRAM_STAFF_CHAT_IDS

BASE_URL = config.BASE_URL

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MotivationLetter)
def notify_telegram_on_motivation_letter_save(sender, instance, created, **kwargs):
    if getattr(instance, "_skip_tg_notify", False):
        return

    if not created and bot and instance.status == 'submitted':
        admin_url = f"{BASE_URL}/admin/core/motivationletter/{instance.pk}/change/"

        message_text = (
            f"Новое мотивационное письмо сохранено:\n"
            f"Пользователь: {instance.user.username}\n"
            f"Дата создания: {instance.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Статус: {instance.get_status_display()}\n"
            f"ID письма: {instance.pk}"
            f"\nПросмотреть: {admin_url}"
        )

        for username, chat_id in TELEGRAM_CHAT_IDS.items():
            try:
                bot.send_message(chat_id, message_text)
                logger.info(f"Telegram уведомление о MotivationLetter отправлено {username} ({chat_id})")
            except Exception as e:
                logger.warning(f"Ошибка при отправке Telegram уведомления о MotivationLetter {username}: {e}")


@receiver(pre_save, sender=MotivationLetter)
def remember_old_rating(sender, instance, **kwargs):
    if instance.pk:
        instance._old_rating = type(instance).objects.filter(pk=instance.pk)\
                              .values_list('admin_rating', flat=True).first()

@receiver(post_save, sender=MotivationLetter)
def notify_on_rating_change(sender, instance, created, **kwargs):
    old_rating = getattr(instance, "_old_rating", None)
    new_rating = getattr(instance, "admin_rating", None)
    rating_changed = (old_rating is None and new_rating is not None) or (old_rating != new_rating)

    if created or not rating_changed:
        return

    user_url = f"{BASE_URL}/motivation/"

    message = build_motivation_rating_message(instance, user_url)

    try:
        send_tg_notification_to_user(message, instance.user)
        logger.info(f"TG: уведомление об оценке письма {instance.pk} отправлено пользователю {instance.user}")
    except Exception as e:
        logger.warning(e)

def build_motivation_rating_message(letter, user_url: str) -> str:
    admin_rating = letter.admin_rating

    return (
        "Ваше мотивационное письмо оценено ✅\n\n"
        f"Комментарий: {admin_rating}\n\n"
        f"Посмотреть письмо: {user_url}"
    )