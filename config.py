import logging
import os
import json

logger = logging.getLogger(__name__)

try:
    CHAT_ID = os.getenv('TELEGRAM_LOG_CHAT_ID')
    logger.info(f'Сообщения в тг отправляются локальному пользователю {CHAT_ID}')
except Exception as e:
    CHAT_ID = None
    logger.error(f'CHAT_ID для дебага не найден {e}')

try:
    raw_dict = os.getenv('TELEGRAM_STAFF_CHAT_IDS')
    TELEGRAM_STAFF_CHAT_IDS = json.loads(raw_dict)
except Exception as e:
    TELEGRAM_STAFF_CHAT_IDS = None
    logger.error(f'TELEGRAM_STAFF_CHAT_IDS не используется {e}')

try:
    TELEGRAM_LOG_CHAT_ID = os.getenv('TELEGRAM_LOG_CHAT_ID')
except Exception as e:
    TELEGRAM_LOG_CHAT_ID = None
    logger.error(f'TELEGRAM_LOG_CHAT_ID не используется {e}')