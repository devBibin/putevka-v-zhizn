import logging


class TelegramHandler(logging.Handler):
    def __init__(self, token, chat_id, level=logging.NOTSET):
        super().__init__(level)
        self.chat_id = chat_id

    def emit(self, record):
        try:
            from core.telegram_tasks import enqueue_admin_message

            message = self.format(record)
            enqueue_admin_message(self.chat_id, message)
        except Exception:
            self.handleError(record)
