import logging
import os

logger = logging.getLogger(__name__)

try:
    CHAT_ID = os.getenv('CHAT_ID')
    logger.info(f'Сообщения в тг отправляются локальному пользователю {CHAT_ID}')
except:
    CHAT_ID = None
    logger.error('CHAT_ID для дебага не найден')

TELEGRAM_STAFF_CHAT_IDS = {
    'developer': CHAT_ID
}

TELEGRAM_LOG_CHAT_ID = CHAT_ID