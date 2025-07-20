import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Document
from telebot import TeleBot
from django.conf import settings
import os

import config as app_config

CHAT_ID = os.getenv('CHAT_ID')
TG_TOKEN = os.getenv("TG_TOKEN")
bot = TeleBot(TG_TOKEN)

TELEGRAM_CHAT_IDS = app_config.TELEGRAM_STAFF_CHAT_IDS

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Document)
def notify_telegram_on_document_upload(sender, instance, created, **kwargs):
    if created and bot:
        document_url = f"/documents/view/{instance.pk}/"

        message_text = (
            f"Новый документ загружен пользователем {instance.user.username}:\n"
            f"Название: {os.path.basename(instance.file.name)}\n"
            f"Описание: {instance.caption}\n"
            f"Доступен по ссылке: http://localhost:8000{document_url}"
        )

        for username, chat_id in TELEGRAM_CHAT_IDS.items():
            try:
                bot.send_message(chat_id, message_text)
                logger.info(f"Уведомление отправлено пользователю {username} (staff) ({chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления Telegram пользователю (staff) {username}: {e}")