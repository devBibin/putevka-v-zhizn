import logging
from telebot import TeleBot
from django.conf import settings

class TelegramHandler(logging.Handler):
    def __init__(self, token, chat_id, level=logging.NOTSET):
        super().__init__(level)
        self.bot = TeleBot(token)
        self.chat_id = chat_id

    def emit(self, record):
        try:
            message = self.format(record)
            self.bot.send_message(self.chat_id, message)
        except Exception:
            self.handleError(record)