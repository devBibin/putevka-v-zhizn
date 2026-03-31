import logging
import os
from typing import Any

import telebot
from telebot import apihelper

import config

logger = logging.getLogger(__name__)

_PROXY_NOT_SET = object()
_configured_proxy: object | str | None = _PROXY_NOT_SET


def configure_telegram_proxy() -> str | None:
    global _configured_proxy

    proxy_url = (
        os.getenv("TELEGRAM_PROXY")
        or os.getenv("OPENAI_PROXY")
        or config.TELEGRAM_PROXY
        or ""
    ).strip() or None
    if _configured_proxy == proxy_url:
        return proxy_url

    apihelper.proxy = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    if proxy_url:
        logger.info("Telegram proxy configured.")

    _configured_proxy = proxy_url
    return proxy_url


def create_telegram_bot(token: str, **kwargs: Any) -> telebot.TeleBot:
    configure_telegram_proxy()
    return telebot.TeleBot(token, **kwargs)
