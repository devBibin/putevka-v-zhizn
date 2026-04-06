import logging
from typing import Any
from urllib.parse import quote

import telebot
from telebot import apihelper

import config

logger = logging.getLogger(__name__)

_PROXY_NOT_SET = object()
_configured_proxy: object | str | None = _PROXY_NOT_SET


def normalize_telegram_proxy_url(raw_proxy_url: str | None) -> str | None:
    proxy_url = (raw_proxy_url or "").strip()
    if not proxy_url:
        return None

    if "://" in proxy_url:
        return proxy_url

    parts = proxy_url.split(":")
    scheme = parts[0].lower()
    if scheme not in {"socks5", "socks5h"}:
        return proxy_url

    if len(parts) == 3:
        _, host, port = parts
        return f"socks5h://{host}:{port}"

    if len(parts) == 4:
        _, host, port, password = parts
        return f"socks5h://:{quote(password, safe='')}@{host}:{port}"

    if len(parts) == 5:
        _, host, port, username, password = parts
        return (
            f"socks5h://{quote(username, safe='')}:"
            f"{quote(password, safe='')}@{host}:{port}"
        )

    logger.warning("Telegram proxy format is not recognized: %s", proxy_url)
    return proxy_url


def configure_telegram_proxy() -> str | None:
    global _configured_proxy

    proxy_url = normalize_telegram_proxy_url(config.TELEGRAM_SOCKS5_PROXY)
    if _configured_proxy == proxy_url:
        return proxy_url

    apihelper.proxy = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    apihelper.session = None
    if proxy_url:
        logger.info("Telegram proxy configured.")

    _configured_proxy = proxy_url
    return proxy_url


def create_telegram_bot(token: str, **kwargs: Any) -> telebot.TeleBot:
    configure_telegram_proxy()
    return telebot.TeleBot(token, **kwargs)
