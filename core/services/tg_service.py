from logging import getLogger

import config
from core.telegram_tasks import enqueue_mail_message

logger = getLogger(__name__)

def send_telegram_feedback_message(text: str) -> None:
    MAX_LEN = 4000

    try:
        for i in range(0, len(text), MAX_LEN):
            enqueue_mail_message(config.TG_CHAT_ID_MAIL, text[i:i + MAX_LEN])
    except Exception as e:
        logger.error(f"{e}")
        raise RuntimeError(f"Telegram queue error: {e}") from e
