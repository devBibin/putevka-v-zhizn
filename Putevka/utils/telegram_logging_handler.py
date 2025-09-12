import json
import logging
from telebot import TeleBot
from django.conf import settings

import config


class TelegramHandler(logging.Handler):
    def __init__(self, token=None, chat_ids=None, level=logging.ERROR):
        super().__init__(level)
        token = token or config.TG_TOKEN_ADMIN
        raw_chat_ids = chat_ids or config.TELEGRAM_STAFF_CHAT_IDS
        self.enabled = bool(token and raw_chat_ids and TeleBot)

        if not self.enabled:
            self.bot = None
            self.chat_ids = []
            return
        try:
            self.bot = TeleBot(token)
        except Exception as e:
            self.bot = None

        if isinstance(raw_chat_ids, str):
            raw_chat_ids = raw_chat_ids.strip()
            if raw_chat_ids.startswith("["):
                try:
                    self.chat_ids = [int(x) for x in json.loads(raw_chat_ids)]
                except Exception:
                    self.chat_ids = []
            else:
                self.chat_ids = [int(x) for x in raw_chat_ids.split(",") if x.strip()]
        elif isinstance(raw_chat_ids, (list, tuple)):
            self.chat_ids = [int(x) for x in raw_chat_ids]
        else:
            self.chat_ids = []

    def emit(self, record):
        try:
            message = self.format(record)
            self.bot.send_message(self.chat_id, message)
        except Exception:
            self.handleError(record)