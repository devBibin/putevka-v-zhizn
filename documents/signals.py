import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Document
from telebot import TeleBot
from django.conf import settings
import os

from telegram_bot_polling import bot

CHAT_ID = os.getenv('CHAT_ID')

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Document)
def notify_telegram_on_document_upload(sender, instance, created, **kwargs):
    if created and bot:
        # telegram_users_to_notify = TelegramUser.objects.filter(user__is_staff=True)

        document_url = f"/documents/view/{instance.pk}/"

        message_text = (
            f"Новый документ загружен пользователем {instance.user.username}:\n"
            f"Название: {os.path.basename(instance.file.name)}\n"
            f"Описание: {instance.caption}\n"
            f"Доступен по ссылке: http://localhost:8000{document_url}"
        )

        # for tg_user in telegram_users_to_notify:
        try:
            bot.send_message(CHAT_ID, message_text)
            # logger.info(f"Уведомление отправлено пользователю {tg_user.user.username} ({tg_user.chat_id})")
        except Exception as e:
            logger.error("Ошибка при отправке уведомления о новом документе пользователю")
            # logger.error(f"Ошибка при отправке уведомления Telegram пользователю {tg_user.user.username}: {e}")