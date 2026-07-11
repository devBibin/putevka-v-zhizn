import logging
import os
from typing import Any

import telebot


logger = logging.getLogger(__name__)


def create_bot(token: str | None, *, parse_mode: str | None = None) -> telebot.TeleBot | None:
    if not token:
        return None
    return telebot.TeleBot(token, parse_mode=parse_mode)


def build_bots() -> dict[str, telebot.TeleBot]:
    bots = {
        "users": create_bot(os.getenv("TG_TOKEN_USERS"), parse_mode="HTML"),
        "admin": create_bot(os.getenv("TG_TOKEN_ADMIN"), parse_mode="HTML"),
        "mail": create_bot(os.getenv("TG_TOKEN_MAIL"), parse_mode="HTML"),
    }
    return {kind: bot for kind, bot in bots.items() if bot is not None}


def to_telebot_markup(payload: dict[str, Any] | None):
    if not payload:
        return None

    markup_type = payload.get("type")
    if markup_type == "inline_keyboard":
        markup = telebot.types.InlineKeyboardMarkup()
        for row in payload.get("inline_keyboard") or []:
            buttons = [
                telebot.types.InlineKeyboardButton(text=button["text"], url=button.get("url"))
                for button in row
            ]
            markup.row(*buttons)
        return markup

    if markup_type == "reply_keyboard":
        markup = telebot.types.ReplyKeyboardMarkup(
            one_time_keyboard=bool(payload.get("one_time_keyboard", True)),
            resize_keyboard=bool(payload.get("resize_keyboard", True)),
        )
        for row in payload.get("keyboard") or []:
            buttons = [
                telebot.types.KeyboardButton(
                    text=button["text"],
                    request_contact=bool(button.get("request_contact", False)),
                )
                for button in row
            ]
            markup.row(*buttons)
        return markup

    if markup_type == "reply_keyboard_remove":
        return telebot.types.ReplyKeyboardRemove()

    logger.warning("Unknown Telegram reply markup type: %s", markup_type)
    return None
