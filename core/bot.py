import logging
from typing import Any

import config
from core.models import RegistrationPersonalData, TelegramAccount
from core.telegram_tasks import (
    enqueue_user_message,
    inline_keyboard_markup,
    remove_keyboard_markup,
    request_contact_markup,
)
from scholar_form.models import UserInfo


logger = logging.getLogger(__name__)


def send_message_to_user(chat_id, message_text, token=None, reply_markup: dict[str, Any] | None = None):
    try:
        enqueue_user_message(chat_id, message_text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.warning("Failed to queue Telegram message to %s: %s", chat_id, e)
        return False


def _message_chat_id(message: dict[str, Any]) -> str | None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    return str(chat_id) if chat_id is not None else None


def _message_from(message: dict[str, Any]) -> dict[str, Any]:
    return message.get("from") or {}


def _save_telegram_profile(telegram_account: TelegramAccount, message: dict[str, Any]) -> None:
    user_data = _message_from(message)
    chat_id = _message_chat_id(message)
    if chat_id and not telegram_account.telegram_id:
        telegram_account.telegram_id = chat_id
    telegram_account.username = user_data.get("username")
    telegram_account.first_name = user_data.get("first_name")
    telegram_account.last_name = user_data.get("last_name")
    telegram_account.language_code = user_data.get("language_code")
    telegram_account.save()


def handle_start(message: dict[str, Any]) -> None:
    chat_id = _message_chat_id(message)
    text = message.get("text") or ""
    if not chat_id:
        logger.warning("Telegram /start update has no chat id")
        return

    parts = text.split(maxsplit=1)
    if len(parts) <= 1:
        send_message_to_user(chat_id, "Привет! Чтобы активировать аккаунт, перейдите по ссылке с сайта.")
        return

    payload = parts[1]
    if not payload.startswith("activate_"):
        send_message_to_user(chat_id, "Неизвестная команда /start.")
        return

    activation_token_str = payload.replace("activate_", "", 1)
    try:
        telegram_account = TelegramAccount.objects.get(activation_token=activation_token_str)

        if telegram_account.telegram_verified and telegram_account.telegram_id:
            send_message_to_user(
                chat_id,
                "Ваш аккаунт Telegram уже привязан и веб-аккаунт активирован!",
            )
            return

        if telegram_account.telegram_id and str(telegram_account.telegram_id) != str(chat_id):
            send_message_to_user(
                chat_id,
                "Этот токен активации привязан к другому Telegram-аккаунту, либо уже был использован.",
            )
            logger.warning("Activation token %s attempted from another Telegram ID %s", activation_token_str, chat_id)
            return

        _save_telegram_profile(telegram_account, message)
        send_message_to_user(
            chat_id,
            (
                f"Привет, {telegram_account.user.username}! Для активации аккаунта на сайте, "
                "пожалуйста, поделитесь своим номером телефона."
            ),
            reply_markup=request_contact_markup("Поделиться своим номером"),
        )
        logger.info("Requested phone for activation token %s user=%s", activation_token_str, telegram_account.user.username)
    except TelegramAccount.DoesNotExist:
        send_message_to_user(chat_id, "Неверный токен активации.")
        logger.warning("Invalid activation token from Telegram ID %s: %s", chat_id, activation_token_str)
    except Exception as e:
        logger.error("Error in Telegram /start handler: %s", e, exc_info=True)
        send_message_to_user(chat_id, "Произошла ошибка при обработке вашего запроса.")


def handle_contact(message: dict[str, Any]) -> None:
    chat_id = _message_chat_id(message)
    contact = message.get("contact")
    if not chat_id:
        logger.warning("Telegram contact update has no chat id")
        return
    if not contact:
        send_message_to_user(chat_id, "Вы не поделились номером телефона.")
        return

    user_data = _message_from(message)
    telegram_id = str(user_data.get("id") or chat_id)
    phone = contact.get("phone_number")

    try:
        telegram_account = TelegramAccount.objects.get(
            telegram_id=telegram_id,
            activation_token__isnull=False,
        )

        telegram_account.username = user_data.get("username")
        telegram_account.first_name = user_data.get("first_name")
        telegram_account.last_name = user_data.get("last_name")
        telegram_account.language_code = user_data.get("language_code")
        telegram_account.user.is_active = True
        telegram_account.telegram_verified = True
        telegram_account.activation_token = None
        telegram_account.save()
        telegram_account.user.save()

        attempt = RegistrationPersonalData.objects.filter(user=telegram_account.user).first()
        user_info = getattr(telegram_account.user, "user_info", None)
        existing_phone_owner = UserInfo.objects.filter(phone=phone).exclude(user=telegram_account.user).first()

        if existing_phone_owner:
            send_message_to_user(chat_id, "Этот номер телефона уже зарегистрирован.")
            return

        if attempt:
            update_fields = ["phone_verified"]
            if not attempt.phone:
                attempt.phone = phone
                update_fields.append("phone")
            attempt.phone_verified = True
            if attempt.current_step != "finish":
                attempt.current_step = "finish"
                update_fields.append("current_step")
            attempt.save(update_fields=update_fields)

        if user_info and (not user_info.phone or user_info.phone == phone):
            user_info.phone = phone
            user_info.save(update_fields=["phone"])

        send_message_to_user(
            chat_id,
            (
                f"Поздравляем, {telegram_account.user.username}! Ваш Telegram-аккаунт успешно привязан! "
                "Теперь вы можете вернуться на сайт и завершить регистрацию."
            ),
            reply_markup=remove_keyboard_markup(),
        )
        logger.info("User %s activated via Telegram ID %s", telegram_account.user.username, telegram_id)
    except TelegramAccount.DoesNotExist:
        send_message_to_user(
            chat_id,
            (
                "Не удалось найти аккаунт, ожидающий активации для этого Telegram ID. "
                "Пожалуйста, убедитесь, что вы нажали ссылку активации на сайте и поделились "
                "своим номером с того же аккаунта Telegram."
            ),
        )
        logger.warning("No activation profile found for Telegram ID %s", telegram_id)
    except Exception as e:
        logger.error("Error in Telegram contact handler: %s", e, exc_info=True)
        send_message_to_user(chat_id, "Произошла ошибка при привязке вашего номера. Пожалуйста, попробуйте еще раз.")


def handle_fallback(message: dict[str, Any]) -> None:
    chat_id = _message_chat_id(message)
    if not chat_id:
        return
    if message.get("text"):
        send_message_to_user(chat_id, f"Вы сказали: {message.get('text')}")
    else:
        send_message_to_user(chat_id, "Я получил нетекстовое сообщение.")


def process_telegram_update(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        logger.debug("Telegram update without message ignored")
        return

    text = message.get("text") or ""
    if text.startswith("/start"):
        handle_start(message)
        return
    if message.get("contact") is not None:
        handle_contact(message)
        return
    handle_fallback(message)


def send_tg_notification_to_user(
    user,
    message: str | None = None,
    url: str | None = None,
    button_text: str = "Открыть",
    disable_preview: bool = True,
):
    # Backward compatibility for old call sites that passed (message, user).
    if isinstance(user, str) and message is not None and not isinstance(message, str):
        user, message = message, user

    tg_id = getattr(getattr(user, "telegram_account", None), "telegram_id", None)
    if not tg_id or not message:
        return False

    markup = None
    if url and config.BASE_URL != "http://localhost:8000":
        markup = inline_keyboard_markup(button_text, url)

    try:
        enqueue_user_message(
            tg_id,
            message,
            reply_markup=markup,
            disable_web_page_preview=disable_preview,
        )
        logger.info("TG: queued message to user %s", tg_id)
        return True
    except Exception as e:
        logger.warning("TG: failed to queue message to user %s: %s", tg_id, e)
        return False
