import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

import config
from core.ai_tasks import enqueue_scholar_video_transcription
from core.signals import TELEGRAM_CHAT_IDS
from core.telegram_proxy import create_telegram_bot
from scholar_form.forms import wizard_done
from scholar_form.models import ScholarVideo

try:
    bot_admin = create_telegram_bot(config.TG_TOKEN_ADMIN)
except Exception:
    bot_admin = None

logger = logging.getLogger(__name__)


@receiver(wizard_done)
def scholar_form_done(sender, instance=None, forms=None, data=None, **kwargs):
    if instance is None:
        return
    username = instance.user
    message_text = (
        f"Анкета успешно заполнена пользователем {username}!\n"
        f"ID анкеты: {instance.pk}"
    )

    if not bot_admin:
        return

    for staff_name, chat_id in TELEGRAM_CHAT_IDS.items():
        try:
            bot_admin.send_message(chat_id, message_text)
            logger.info("Scholar form completion notification sent to %s", staff_name)
        except Exception as e:
            logger.error("Failed to send scholar form completion notification to %s: %s", staff_name, e)


@receiver(post_save, sender=ScholarVideo)
def enqueue_scholar_video_ai_task(sender, instance: ScholarVideo, **kwargs):
    try:
        enqueue_scholar_video_transcription(instance)
    except Exception as e:
        logger.warning("Failed to enqueue scholar video AI task for %s: %s", instance.pk, e)
