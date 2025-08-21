import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from telebot import TeleBot
from django.conf import settings
import os

import config
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
                logger.error(f"Ошибка при отправке Telegram уведомления о MotivationLetter {username}: {e}")