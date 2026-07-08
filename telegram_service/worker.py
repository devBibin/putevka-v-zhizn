import logging
import os
import threading
import time

import requests

from telegram_service.client import DjangoTelegramClient
from telegram_service.telegram_runtime import build_bots, to_telebot_markup


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="[%(levelname)s] %(asctime)s %(name)s:%(lineno)s %(message)s",
)
logger = logging.getLogger(__name__)

POLLING_INTERVAL = int(os.getenv("TELEGRAM_WORKER_POLLING_INTERVAL", "5"))
LEASE_SECONDS = int(os.getenv("TELEGRAM_WORKER_LEASE_SECONDS", "120"))


def run_update_polling(client: DjangoTelegramClient, users_bot):
    if users_bot is None:
        logger.warning("TG_TOKEN_USERS is not set; incoming Telegram polling is disabled")
        return

    users_bot.remove_webhook()

    @users_bot.message_handler(func=lambda message: True, content_types=["text", "contact", "video", "document"])
    def handle_message(message):
        update = {
            "update_id": message.json.get("message_id"),
            "message": message.json,
        }
        try:
            client.submit_update(update)
            logger.debug("Submitted Telegram update message_id=%s", update["update_id"])
        except Exception:
            logger.exception("Failed to submit Telegram update message_id=%s", update["update_id"])

    logger.info("Telegram users bot polling started")
    users_bot.infinity_polling()


def send_message(bots: dict, message: dict) -> None:
    bot_kind = message["bot_kind"]
    bot = bots.get(bot_kind)
    if bot is None:
        raise RuntimeError(f"Telegram bot token is not configured for kind={bot_kind}")

    bot.send_message(
        chat_id=message["chat_id"],
        text=message["text"],
        reply_markup=to_telebot_markup(message.get("reply_markup")),
        parse_mode=message.get("parse_mode") or None,
        disable_web_page_preview=bool(message.get("disable_web_page_preview", True)),
    )


def run_outgoing_worker(client: DjangoTelegramClient, bots: dict):
    logger.info(
        "Telegram outgoing worker started worker_id=%s base_url=%s polling_interval=%ss lease=%ss",
        client.worker_id,
        client.base_url,
        POLLING_INTERVAL,
        LEASE_SECONDS,
    )
    while True:
        try:
            message = client.claim(LEASE_SECONDS)
        except requests.RequestException:
            logger.warning("Django Telegram API is unavailable, retrying in %ss", POLLING_INTERVAL, exc_info=True)
            time.sleep(POLLING_INTERVAL)
            continue

        if not message:
            time.sleep(POLLING_INTERVAL)
            continue

        task_id = message["id"]
        try:
            send_message(bots, message)
            client.complete(task_id)
            logger.info("Sent Telegram message task_id=%s bot=%s chat_id=%s", task_id, message["bot_kind"], message["chat_id"])
        except Exception as exc:
            logger.exception("Failed Telegram message task_id=%s", task_id)
            try:
                client.fail(task_id, str(exc), retryable=True)
            except Exception:
                logger.exception("Failed to report Telegram message failure task_id=%s", task_id)


def main():
    client = DjangoTelegramClient()
    bots = build_bots()

    update_thread = threading.Thread(target=run_update_polling, args=(client, bots.get("users")), daemon=True)
    update_thread.start()
    run_outgoing_worker(client, bots)


if __name__ == "__main__":
    main()
