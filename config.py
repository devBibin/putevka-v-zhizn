import json
import logging
import os

logger = logging.getLogger(__name__)


def get_variable(name: str):
    try:
        value = os.getenv(name)
        logger.info(f'{name} установлен')
        return value
    except Exception as e:
        logger.info(f'{name} не установлен {e}')
        return None


CHAT_ID = get_variable('CHAT_ID')

try:
    raw_dict = get_variable('TELEGRAM_STAFF_CHAT_IDS')
    TELEGRAM_STAFF_CHAT_IDS = json.loads(raw_dict)
except Exception as e:
    TELEGRAM_STAFF_CHAT_IDS = None
    logger.error(f'TELEGRAM_STAFF_CHAT_IDS не используется {e}')

TELEGRAM_LOG_CHAT_ID = get_variable('TELEGRAM_LOG_CHAT_ID')
TG_TOKEN_ADMIN = get_variable('TG_TOKEN_ADMIN')
TG_TOKEN_USERS = get_variable('TG_TOKEN_USERS')
TG_BOT_USERS_USERNAME = get_variable('TG_BOT_USERS_USERNAME')

GPT_TOKEN = get_variable('GPT_TOKEN')

PUBLIC_KEY_CALL = get_variable('PUBLIC_KEY_CALL')
CAMPAIGN_ID = get_variable('CAMPAIGN_ID')
ZVONOK_API_INITIATE_URL = get_variable('ZVONOK_API_INITIATE_URL')
ZVONOK_API_POLLING_URL = get_variable('ZVONOK_API_POLLING_URL')

BASE_URL = get_variable('BASE_URL')