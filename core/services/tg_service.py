from logging import getLogger

import config
from core.telegram_proxy import create_telegram_bot

logger = getLogger(__name__)

_bot = create_telegram_bot(config.TG_TOKEN_MAIL, parse_mode="HTML")

def send_telegram_feedback_message(text: str) -> None:
    MAX_LEN = 4000

    try:
        for i in range(0, len(text), MAX_LEN):
            _bot.send_message(
                chat_id=config.TG_CHAT_ID_MAIL,
                text=text[i:i + MAX_LEN],
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"{e}")
        raise RuntimeError(f"Telegram API error: {e}") from e
