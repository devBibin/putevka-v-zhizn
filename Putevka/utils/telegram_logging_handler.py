import logging
import os

from telebot import TeleBot, apihelper


def _configure_telegram_proxy() -> None:
    proxy_url = (os.getenv("TELEGRAM_PROXY") or os.getenv("OPENAI_PROXY") or "").strip()
    apihelper.proxy = {"http": proxy_url, "https": proxy_url} if proxy_url else None

class TelegramHandler(logging.Handler):
    def __init__(self, token, chat_id, level=logging.NOTSET):
        super().__init__(level)
        _configure_telegram_proxy()
        self.bot = TeleBot(token)
        self.chat_id = chat_id

    def emit(self, record):
        try:
            message = self.format(record)
            self.bot.send_message(self.chat_id, message)
        except Exception:
            self.handleError(record)
