import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import TelegramMessageTask


logger = logging.getLogger(__name__)


def inline_keyboard_markup(text: str, url: str) -> dict[str, Any]:
    return {
        "type": "inline_keyboard",
        "inline_keyboard": [[{"text": text, "url": url}]],
    }


def request_contact_markup(text: str) -> dict[str, Any]:
    return {
        "type": "reply_keyboard",
        "one_time_keyboard": True,
        "resize_keyboard": True,
        "keyboard": [[{"text": text, "request_contact": True}]],
    }


def remove_keyboard_markup() -> dict[str, Any]:
    return {"type": "reply_keyboard_remove"}


def enqueue_telegram_message(
    *,
    bot_kind: str,
    chat_id: str | int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> TelegramMessageTask:
    task = TelegramMessageTask.objects.create(
        bot_kind=bot_kind,
        chat_id=str(chat_id),
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )
    logger.info("Queued Telegram message task_id=%s bot=%s chat_id=%s", task.pk, bot_kind, chat_id)
    return task


def enqueue_user_message(
    chat_id: str | int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> TelegramMessageTask:
    return enqueue_telegram_message(
        bot_kind=TelegramMessageTask.BotKind.USERS,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


def enqueue_admin_message(chat_id: str | int, text: str) -> TelegramMessageTask:
    return enqueue_telegram_message(
        bot_kind=TelegramMessageTask.BotKind.ADMIN,
        chat_id=chat_id,
        text=text,
    )


def enqueue_mail_message(chat_id: str | int, text: str) -> TelegramMessageTask:
    return enqueue_telegram_message(
        bot_kind=TelegramMessageTask.BotKind.MAIL,
        chat_id=chat_id,
        text=text,
    )


def claim_next_telegram_message(worker_id: str, lease_seconds: int) -> TelegramMessageTask | None:
    now = timezone.now()
    locked_until = now + timedelta(seconds=lease_seconds)

    with transaction.atomic():
        task = (
            TelegramMessageTask.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status=TelegramMessageTask.Status.PENDING)
                | Q(status=TelegramMessageTask.Status.RETRY, locked_until__lte=now)
                | Q(status=TelegramMessageTask.Status.RETRY, locked_until__isnull=True)
                | Q(status=TelegramMessageTask.Status.PROCESSING, locked_until__lte=now)
            )
            .order_by("created_at")
            .first()
        )
        if not task:
            return None

        task.status = TelegramMessageTask.Status.PROCESSING
        task.locked_by = worker_id
        task.locked_until = locked_until
        task.attempts += 1
        task.save(update_fields=["status", "locked_by", "locked_until", "attempts", "updated_at"])
        return task


def serialize_telegram_message(task: TelegramMessageTask) -> dict[str, Any]:
    return {
        "id": str(task.pk),
        "bot_kind": task.bot_kind,
        "chat_id": task.chat_id,
        "text": task.text,
        "reply_markup": task.reply_markup,
        "parse_mode": task.parse_mode,
        "disable_web_page_preview": task.disable_web_page_preview,
        "attempts": task.attempts,
        "locked_until": task.locked_until.isoformat() if task.locked_until else None,
    }


def complete_telegram_message(task_id: str, worker_id: str) -> TelegramMessageTask:
    task = TelegramMessageTask.objects.get(pk=task_id)
    if task.locked_by and task.locked_by != worker_id:
        raise ValueError("Telegram message task is locked by another worker")
    task.status = TelegramMessageTask.Status.SENT
    task.sent_at = timezone.now()
    task.locked_by = ""
    task.locked_until = None
    task.error = ""
    task.save(update_fields=["status", "sent_at", "locked_by", "locked_until", "error", "updated_at"])
    return task


def fail_telegram_message(task_id: str, worker_id: str, error: str, retryable: bool = True) -> TelegramMessageTask:
    task = TelegramMessageTask.objects.get(pk=task_id)
    if task.locked_by and task.locked_by != worker_id:
        raise ValueError("Telegram message task is locked by another worker")
    task.error = error[:4000]
    task.locked_by = ""
    task.locked_until = None
    if retryable and task.attempts < task.max_attempts:
        task.status = TelegramMessageTask.Status.RETRY
    else:
        task.status = TelegramMessageTask.Status.FAILED
    task.save(update_fields=["status", "error", "locked_by", "locked_until", "updated_at"])
    return task
