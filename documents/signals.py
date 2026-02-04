import logging
import os

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from telebot import TeleBot

import config
from core.bot import send_tg_notification_to_user
from core.models import UserNotification
from core.services.email_service import send_email_to_user
from .models import Document

TG_TOKEN_ADMIN = config.TG_TOKEN_ADMIN

try:
    bot_admin = TeleBot(TG_TOKEN_ADMIN)
except:
    bot_admin = None

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
            f"Доступен по ссылке: {BASE_URL}{document_url}\n"
            f"Загружен персоналом: {'да' if instance.uploaded_by_staff else 'нет'}"
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
            f"Пользователь {instance.user.username} прикрепил документы:\n"
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

    document_name = old.caption or os.path.basename(old.file.name)
    full_url = f"{BASE_URL}{document_url}"

    message_text = (
        f"Изменён статус документа:\n"
        f"Документ: '{old.caption or os.path.basename(old.file.name)}'\n"
        f"Статус: {old_display} → {new_display}\n"
        f"Ссылка: {BASE_URL}{document_url}"
    )

    send_tg_notification_to_user(message_text, instance.user, url=f"{BASE_URL}{document_url}",
                                 button_text="Открыть документ")

    send_email_to_user(
        subject="Изменён статус документа",
        user=instance.user,
        text=(
            "Изменён статус документа.\n\n"
            f"Документ: {document_name}\n"
            f"Статус: {old_display} → {new_display}\n"
            f"Открыть: {full_url}\n"
        ),
        html=(
            "<b>Изменён статус документа</b><br><br>"
            f"Документ: <b>{document_name}</b><br>"
            f"Статус: {old_display} → <b>{new_display}</b><br>"
            f"<a href='{full_url}'>Открыть документ</a>"
        ),
    )

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
        "📬 <b>Новое уведомление!</b>\n\n"
        f"{notif.message}\n\n"
        f"👤 <b>Отправитель:</b> {notif.sender}\n"
        f"🕒 <b>Время:</b> {notif.created_at:%d.%m.%Y %H:%M}"
    )

    site_url = f"{BASE_URL}"

    def _send():
        send_tg_notification_to_user(
            user,
            msg,
            url=site_url,
            button_text="🌐 Открыть сайт",
        )
        logger.debug(
            f"TG уведомление (through) отправлено {user.username} "
            f"по Notification(id={notif.pk})"
        )

        send_email_to_user(
            subject="Новое уведомление",
            user=user,
            text=(
                "У вас новое уведомление.\n\n"
                f"{notif.message}\n\n"
                f"Отправитель: {notif.sender}\n"
                f"Время: {notif.created_at:%d.%m.%Y %H:%M}\n\n"
                f"Открыть сайт: {site_url}"
            ),
            html=(
                "<b>📬 Новое уведомление!</b><br><br>"
                f"{notif.message}<br><br>"
                f"<b>Отправитель:</b> {notif.sender}<br>"
                f"<b>Время:</b> {notif.created_at:%d.%m.%Y %H:%M}<br><br>"
                f"<a href='{site_url}'>🌐 Открыть сайт</a>"
            ),
        )

    from django.db import transaction
    transaction.on_commit(_send)
