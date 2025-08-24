import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver, Signal

from core.bot import send_tg_notification_to_user
from core.models import Notification, UserNotification
from .models import Document
from telebot import TeleBot
from django.conf import settings
import os

import config

TG_TOKEN_ADMIN = config.TG_TOKEN_ADMIN
bot_admin = TeleBot(TG_TOKEN_ADMIN)

TG_TOKEN_USERS = config.TG_TOKEN_USERS
TELEGRAM_CHAT_IDS = config.TELEGRAM_STAFF_CHAT_IDS

BASE_URL = config.BASE_URL

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Document)
def notify_telegram_on_document_upload(sender, instance, created, **kwargs):
    if created and bot_admin:
        document_url = f"/documents/view/{instance.pk}/"

        message_text = (
            f"Новый документ загружен пользователем {instance.user.username}:\n"
            f"Название: {os.path.basename(instance.file.name)}\n"
            f"Описание: {instance.caption}\n"
            f"Доступен по ссылке: {BASE_URL}{document_url}"
        )

        for username, chat_id in TELEGRAM_CHAT_IDS.items():
            try:
                bot_admin.send_message(chat_id, message_text)
                logger.info(f"Уведомление отправлено пользователю {username} (staff) ({chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления Telegram пользователю (staff) {username}: {e}")


@receiver(post_save, sender=Document)
def notify_telegram_on_documents_attached(sender, instance, created, **kwargs):
    if not created and bot_admin:
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
                bot_admin.send_message(chat_id, message_text)
                logger.info(f"Telegram уведомление о прикреплении документов отправлено {username} ({chat_id})")
            except Exception as e:
                logger.error(f"Ошибка при отправке Telegram уведомления о прикреплении документов {username}: {e}")

@receiver(pre_save, sender=Document)
def notify_telegram_on_status_change(sender, instance: Document, **kwargs):
    if not instance.pk:
        return

    try:
        old = sender.objects.only("status", "caption", "file", "user").get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old.status == instance.status:
        return

    document_url = f"/documents/view/{instance.pk}/"
    old_display = instance.get_status_display() if hasattr(instance, "get_status_display") else instance.status
    try:
        choices = dict(Document._meta.get_field("status").choices)
        old_display = choices.get(old.status, old.status)
        new_display = choices.get(instance.status, instance.status)
    except Exception:
        old_display = old.status
        new_display = instance.status

    message_text = (
        f"Изменён статус документа:\n"
        f"Документ: '{old.caption or os.path.basename(old.file.name)}'\n"
        f"Статус: {old_display} → {new_display}\n"
        f"Ссылка: {BASE_URL}{document_url}"
    )

    send_tg_notification_to_user(message_text, instance.user)

    logger.info(
        f"Статус документа ID={instance.pk} изменён: {old.status} -> {instance.status}"
    )

@receiver(post_save, sender=UserNotification)
def notify_telegram_on_notification(sender, instance, created, **kwargs):
    if not created:
        return

    notif = instance.notification
    user = instance.recipient

    msg = (
        f"Вам пришло новое уведомление!\n\n"
        f"{notif.message}\n\n"
        f"от {notif.sender} в {notif.created_at:%Y-%m-%d %H:%M}"
    )

    def _send():
        send_tg_notification_to_user(msg, user)
        logger.debug(f"TG уведомление (through) отправлено {user.username} по Notification(id={notif.pk})")

    from django.db import transaction
    transaction.on_commit(_send)
