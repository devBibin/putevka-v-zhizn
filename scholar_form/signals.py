import logging

from django.dispatch import receiver

import config
from core.bot import send_tg_notification_to_user
from core.signals import TELEGRAM_CHAT_IDS
from core.telegram_proxy import create_telegram_bot
from scholar_form.forms import wizard_done

try:
    bot_admin = create_telegram_bot(config.TG_TOKEN_ADMIN)
except:
    bot_admin = None

logger = logging.getLogger(__name__)

@receiver(wizard_done)
def scholar_form_done(sender, instance=None, forms=None, data=None, **kwargs):
    username = instance.user
    message_text = (
        f"Анкета успешно заполнена пользователем {username}!\n"
        f"ID анкеты: {instance.pk}"
    )

    for username, chat_id in TELEGRAM_CHAT_IDS.items():
        try:
            bot_admin.send_message(chat_id, message_text)
            logger.info(f"Пользователь {username} заполнил анкету")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о завершённой анкете {username}: {e}")


