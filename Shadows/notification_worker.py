import os
import time
import logging

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Putevka.settings")
django.setup()

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.bot import send_tg_notification_to_user
from core.services.email_service import send_email_to_user

from django.conf import settings
from core.models import UserNotification

from django.db import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notifications_worker")

POLL_SECONDS = int(os.getenv("NOTIF_POLL_SECONDS", "5"))
BATCH_SIZE = int(os.getenv("NOTIF_BATCH_SIZE", "100"))
BASE_URL = getattr(settings, "BASE_URL", "")


def process_batch():
    now = timezone.now()

    with transaction.atomic():
        ids = list(
            UserNotification.objects
            .select_for_update(skip_locked=True, of=("self",))
            .filter(Q(tg_sent_at__isnull=True) | Q(email_sent_at__isnull=True))
            .order_by("id")
            .values_list("id", flat=True)[:BATCH_SIZE]
        )

    if not ids:
        return 0

    items = list(
        UserNotification.objects
        .filter(id__in=ids)
        .select_related("notification", "recipient", "notification__sender")
        .order_by("id")
    )

    sent = 0

    for item in items:
        notif = item.notification
        user = item.recipient

        msg = (
            "📬 <b>Новое уведомление!</b>\n\n"
            f"{notif.message}\n\n"
            f"👤 <b>Отправитель:</b> {notif.sender}\n"
        )

        try:
            UserNotification.objects.filter(pk=item.pk).update(
                send_attempts=models.F("send_attempts") + 1
            )

            if item.tg_sent_at is None:
                send_tg_notification_to_user(
                    user,
                    msg,
                    url=BASE_URL,
                    button_text="🌐 Открыть сайт",
                )
                updated = UserNotification.objects.filter(pk=item.pk, tg_sent_at__isnull=True).update(
                    tg_sent_at=now,
                    last_error="",
                )
                if updated:
                    logger.info(f"TG sent to {user.username} (id={item.pk})")

            if item.email_sent_at is None:
                send_email_to_user(
                    subject="Новое уведомление",
                    user=user,
                    text=(
                        "У вас новое уведомление.\n\n"
                        f"{notif.message}\n\n"
                        f"Отправитель: {notif.sender}\n"
                        f"Открыть сайт: {BASE_URL}"
                    ),
                    html=(
                        "<b>📬 Новое уведомление!</b><br><br>"
                        f"{notif.message}<br><br>"
                        f"<b>Отправитель:</b> {notif.sender}<br>"
                        f"<a href='{BASE_URL}'>🌐 Открыть сайт</a>"
                    ),
                )
                updated = UserNotification.objects.filter(pk=item.pk, email_sent_at__isnull=True).update(
                    email_sent_at=now,
                    last_error="",
                )
                if updated:
                    logger.info(f"Email sent to {user.username} (id={item.pk})")

            sent += 1

        except Exception as e:
            logger.exception(f"Error sending notification id={item.pk}: {e}")
            UserNotification.objects.filter(pk=item.pk).update(
                last_error=str(e)
            )

    return sent


def main():
    logger.info("Notifications worker started")

    while True:
        try:
            sent = process_batch()
            if sent == 0:
                time.sleep(POLL_SECONDS)
        except Exception as e:
            logger.exception(f"Worker crashed loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()