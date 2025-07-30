import logging

from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from .models import Document
from telebot import TeleBot
from django.conf import settings
import os

import config as app_config

CHAT_ID = os.getenv('TELEGRAM_LOG_CHAT_ID')
TG_TOKEN = os.getenv("TG_TOKEN_ADMIN")
bot = TeleBot(TG_TOKEN)

TELEGRAM_CHAT_IDS = app_config.TELEGRAM_STAFF_CHAT_IDS

BASE_URL = os.getenv('BASE_URL')

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Document)
def notify_telegram_on_document_upload(sender, instance, created, **kwargs):
    if created and bot:
        document_url = f"/documents/view/{instance.pk}/"

        message_text = (
            f"Новый документ загружен пользователем {instance.user.username}:\n"
            f"Название: {os.path.basename(instance.file.name)}\n"
            f"Описание: {instance.caption}\n"
            f"Доступен по ссылке: {BASE_URL}{document_url}"
        )

        for username, chat_id in TELEGRAM_CHAT_IDS.items():
            try:
                bot.send_message(chat_id, message_text)
                logger.info(f"Уведомление отправлено пользователю {username} (staff) ({chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления Telegram пользователю (staff) {username}: {e}")


@receiver(post_save, sender=Document)
def notify_telegram_on_documents_attached(sender, instance, **kwargs):
    if bot:
        document_url = f"/documents/view/{instance.pk}/"

        attached_docs_names = [
            f"{doc.user_file_name}({doc.caption})" for doc in instance.related_documents.all()
        ]
        attached_docs_list = "\n- ".join(attached_docs_names) if attached_docs_names else "нет"

        message_text = (
            f"Пользователь { instance.user.username} прикрепил документы:\n"
            f"К документу: '{instance.caption or os.path.basename(instance.file.name)}' (ID: {instance.pk})\n"
            f"Новый статус документа: {instance.get_status_display()}\n"
            f"Прикрепленные документы:\n- {attached_docs_list}\n"
            f"Ссылка на основной документ: {BASE_URL}{document_url}"
        )

        for username, chat_id in TELEGRAM_CHAT_IDS.items():
            try:
                bot.send_message(chat_id, message_text)
                logger.info(f"Telegram уведомление о прикреплении документов отправлено {username} ({chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке Telegram уведомления о прикреплении документов {username}: {e}")