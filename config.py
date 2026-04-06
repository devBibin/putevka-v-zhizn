import json
import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


def configure_telegram_proxy(proxy_url: str | None) -> None:
    proxy_url = (proxy_url or "").strip()
    if not proxy_url:
        return

    try:
        from telebot import apihelper
    except Exception as e:
        logger.warning(f'Не удалось импортировать telebot.apihelper для SOCKS5 proxy: {e}')
        return

    apihelper.proxy = {
        'http': proxy_url,
        'https': proxy_url,
    }
    apihelper.session = None
    logger.info('TELEGRAM_SOCKS5_PROXY configured for TeleBot')


def get_variable(name: str):
    try:
        value = os.getenv(name)
        logger.info(f'{name} установлен')
        return value
    except Exception as e:
        logger.info(f'{name} не установлен {e}')
        return None


try:
    raw_dict = get_variable('TELEGRAM_STAFF_CHAT_IDS')
    TELEGRAM_STAFF_CHAT_IDS = json.loads(raw_dict)
except Exception as e:
    TELEGRAM_STAFF_CHAT_IDS = ""
    logger.error(f'TELEGRAM_STAFF_CHAT_IDS не используется {e}')

TELEGRAM_LOG_CHAT_ID = get_variable('TELEGRAM_LOG_CHAT_ID')
TG_TOKEN_ADMIN = get_variable('TG_TOKEN_ADMIN')
TG_TOKEN_USERS = get_variable('TG_TOKEN_USERS')
TG_BOT_USERS_USERNAME = get_variable('TG_BOT_USERS_USERNAME')
TELEGRAM_SOCKS5_PROXY = get_variable('TELEGRAM_SOCKS5_PROXY')

TG_TOKEN_MAIL = get_variable('TG_TOKEN_MAIL')
TG_CHAT_ID_MAIL = get_variable('TG_CHAT_ID_MAIL')

GPT_TOKEN = get_variable('GPT_TOKEN')

PUBLIC_KEY_CALL = get_variable('PUBLIC_KEY_CALL')
CAMPAIGN_ID = get_variable('CAMPAIGN_ID')
ZVONOK_API_INITIATE_URL = get_variable('ZVONOK_API_INITIATE_URL')
ZVONOK_API_POLLING_URL = get_variable('ZVONOK_API_POLLING_URL')

BASE_URL = get_variable('BASE_URL')

configure_telegram_proxy(TELEGRAM_SOCKS5_PROXY)

MAX_VIDEO_MB = 2000
