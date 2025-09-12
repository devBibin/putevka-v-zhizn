import json
import logging
from pathlib import Path

import telebot
import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from telebot import TeleBot

import config
from core.models import TelegramAccount, RegistrationPersonalData
from scholar_form.models import UserInfo, VideoSubmission

logger = logging.getLogger('django.request')

bot_instances = {}

def send_message_to_user(chat_id, message_text, token):
    try:
        bot_instances[token].send_message(chat_id, message_text)
    except Exception as e:
        logger.warning(e)

def get_bot_messenger():
    global _bot_messenger
    if _bot_messenger is None:
        if not config.TG_TOKEN_USERS:
            logger.error("TG_TOKEN_USERS не установлен в config.py")
            return None
        _bot_messenger = telebot.TeleBot(config.TG_TOKEN_USERS)
    return _bot_messenger


def get_bot_instance(token):
    if token not in bot_instances:
        try:
            bot_instances[token] = telebot.TeleBot(token, parse_mode='HTML')
        except Exception as e:
            logger.error(f'Невозможно подключиться к телеграмм-боту: {e}')
            return None

        @bot_instances[token].message_handler(commands=['start'])
        def handle_start(message):
            if message.text and len(message.text.split()) > 1:
                payload = message.text.split(' ')[1]
                if payload.startswith('activate_'):
                    activation_token_str = payload.replace('activate_', '')
                    try:
                        telegram_account = TelegramAccount.objects.get(activation_token=activation_token_str)

                        if telegram_account.telegram_verified:
                            send_message_to_user(message.chat.id,
                                                              "Ваш аккаунт Telegram уже привязан и веб-аккаунт активирован!", token)
                            return

                        if telegram_account.telegram_id and str(telegram_account.telegram_id) != str(message.chat.id):
                            send_message_to_user(message.chat.id,
                                                              "Этот токен активации привязан к другому Telegram-аккаунту, либо уже был использован.", token)
                            logger.warning(
                                f"Попытка активации токена {activation_token_str} с другого Telegram ID ({message.chat.id}).")
                            return

                        if not telegram_account.telegram_id:
                            telegram_account.telegram_id = str(message.chat.id)
                        telegram_account.username = message.from_user.username
                        telegram_account.first_name = message.from_user.first_name
                        telegram_account.last_name = message.from_user.last_name
                        telegram_account.language_code = message.from_user.language_code
                        telegram_account.save()

                        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
                        button_phone = telebot.types.KeyboardButton(text="Поделиться своим номером",
                                                                    request_contact=True)
                        markup.add(button_phone)

                        try:
                            bot_instances[token].send_message(message.chat.id,
                                                              f"Привет, {telegram_account.user.username}! Для активации аккаунта на сайте, пожалуйста, поделитесь своим номером телефона.",
                                                              reply_markup=markup)
                        except Exception as e:
                            logger.warning(f"Ошибка при отправке сообщения с запросом номера телефона: {e}")

                        logger.info(
                            f"Запрошен номер телефона для активации токена {activation_token_str} для пользователя {telegram_account.user.username}")

                    except TelegramAccount.DoesNotExist:
                        send_message_to_user(message.chat.id, "Неверный токен активации.", token)
                        logger.warning(
                            f"Неверный токен активации от Telegram ID {message.chat.id}: {activation_token_str}")
                    except Exception as e:
                        logger.error(f"Ошибка в handle_start с токеном: {e}", exc_info=True)
                        send_message_to_user(message.chat.id,
                                                          "Произошла ошибка при обработке вашего запроса.", token)
                else:
                    send_message_to_user(message.chat.id, "Неизвестная команда /start.", token)
            else:
                send_message_to_user(message.chat.id,
                                                  "Привет! Чтобы активировать аккаунт, перейдите по ссылке с сайта.", token)

        @bot_instances[token].message_handler(content_types=['contact'])
        def handle_contact(message):
            if message.contact is not None:
                telegram_id = str(message.from_user.id)
                phone = message.contact.phone_number

                try:
                    telegram_account = TelegramAccount.objects.get(
                        telegram_id=telegram_id,
                        telegram_verified=False,
                        activation_token__isnull=False
                    )

                    telegram_account.username = message.from_user.username
                    telegram_account.first_name = message.from_user.first_name
                    telegram_account.last_name = message.from_user.last_name
                    telegram_account.language_code = message.from_user.language_code

                    telegram_account.user.is_active = True
                    telegram_account.telegram_verified = True
                    telegram_account.activation_token = None

                    telegram_account.save()
                    telegram_account.user.save()

                    attempt = RegistrationPersonalData.objects.filter(user=telegram_account.user).first()

                    user = UserInfo.objects.filter(phone=phone).first()

                    if user:
                        bot_instances[token].send_message(message.chat.id,
                                                          f'Этот номер телефона уже зарегистрирован.')
                        return None

                    if attempt:
                        attempt.phone = phone
                        attempt.user.user_info.phone = phone
                        attempt.user.user_info.email = user.email
                        attempt.user.user_info.save()
                        attempt.phone_verified = True
                        attempt.current_step = 'finish'
                        attempt.save()

                    try:
                        bot_instances[token].send_message(message.chat.id,
                                                          f"Поздравляем, {telegram_account.user.username}! Ваш Telegram-аккаунт успешно привязан! Теперь вы можете вернуться на сайт и завершить регистрацию.",
                                                          reply_markup=telebot.types.ReplyKeyboardRemove())
                    except Exception as e:
                        logger.warning(f"Сообщение не отправилось пользователю: {e}")
                    logger.info(
                        f"Аккаунт пользователя {telegram_account.user.username} успешно активирован через Telegram ID {telegram_id}.")

                except TelegramAccount.DoesNotExist:
                    send_message_to_user(message.chat.id,
                                                      "Не удалось найти аккаунт, ожидающий активации для этого Telegram ID. Пожалуйста, убедитесь, что вы нажали ссылку активации на сайте и поделились своим номером с того же аккаунта Telegram.", token)
                    logger.warning(f"Не удалось найти профиль для активации от Telegram ID {telegram_id}.")
                except Exception as e:
                    logger.error(f"Ошибка при обработке контакта: {e}", exc_info=True)
                    send_message_to_user(message.chat.id,
                                                      "Произошла ошибка при привязке вашего номера. Пожалуйста, попробуйте еще раз.", token)
            else:
                send_message_to_user(message.chat.id, "Вы не поделились номером телефона.", token)

        @bot_instances[token].message_handler(content_types=['video', 'document'])
        def handle_video(message):
            tg_id = str(message.from_user.id)

            tg_acc = TelegramAccount.objects.get(telegram_id=tg_id)
            try:
                user = tg_acc.user
            except TelegramAccount.DoesNotExist:
                user = None
            if not user:
                bot_instances[token].reply_to(message, "Сначала свяжите ваш Telegram на сайте (в профиле есть кнопка привязки).")
                return

            file_id = None
            original_name = ""
            mime_type = ""
            duration = 0
            size_bytes = 0

            if message.video:
                file_id = message.video.file_id
                duration = message.video.duration or 0
                mime_type = getattr(message.video, "mime_type", "") or ""
                size_bytes = getattr(message.video, "file_size", 0) or 0
                original_name = "video.mp4"
            elif message.document:
                file_id = message.document.file_id
                mime_type = getattr(message.document, "mime_type", "") or ""
                size_bytes = getattr(message.document, "file_size", 0) or 0
                original_name = message.document.file_name or "video.bin"
            else:
                bot_instances[token].reply_to(message, "Отправьте, пожалуйста, видео или документ с видео.")
                return

            bot_instances[token].reply_to(message, "Подождите, видео загружается...")

            if config.MAX_VIDEO_MB and size_bytes and size_bytes > config.MAX_VIDEO_MB * 1024 * 1024:
                bot_instances[token].reply_to(message, f"Файл слишком большой. Разрешено до {config.MAX_VIDEO_MB} МБ.")
                return

            try:
                f = bot_instances[token].get_file(file_id)
            except Exception as e:
                bot_instances[token].reply_to(message, "Не удалось получить файл из Telegram. Попробуйте ещё раз.")
                return

            try:
                data = _download_from_tg(f.file_path)
            except Exception:
                bot_instances[token].reply_to(message, "Ошибка скачивания файла. Попробуйте ещё раз.")
                return

            ext = Path(original_name).suffix.lower() or ".mp4"
            if ext not in [".mp4", ".mov", ".mkv", ".webm"]:
                ext = ".mp4"

            vs = VideoSubmission.objects.create(
                user=user,
                tg_user_id=tg_id,
                tg_file_id=file_id,
                tg_file_path=f.file_path,
                original_filename=original_name,
                mime_type=mime_type,
                size_bytes=len(data) or size_bytes,
                duration_sec=duration,
                status=VideoSubmission.Status.RECEIVED,
            )

            rel_path = f"videos/{user.id}/{vs.id}{ext}"
            saved_path = default_storage.save(rel_path, ContentFile(data))

            vs.file.name = saved_path
            vs.status = VideoSubmission.Status.SAVED
            vs.save(update_fields=["file", "status"])

            bot_instances[token].reply_to(message, "Видео получено! ✅ Зайдите на сайт — оно уже прикреплено к анкете.")

        @bot_instances[token].message_handler(func=lambda message: True)
        def echo_all(message):
            try:
                if message.text:
                    bot_instances[token].reply_to(message, f"Вы сказали: {message.text}")
                    logger.info(f"Повтор сообщения '{message.text}' пользователю {message.from_user.id}")
                else:
                    bot_instances[token].reply_to(message, "Я получил нетекстовое сообщение.")
                    logger.warning(f"Получено нетекстовое сообщение от {message.from_user.id}")
            except Exception as e:
                logger.error(f"Ошибка при повторе сообщения: {e}")

    logger.info(f"Инициализирован новый экземпляр бота для токена: {token[:5]}...")
    return bot_instances[token]


@csrf_exempt
def webhook(request, bot_token):
    if request.method == 'POST':
        try:
            json_string = request.body.decode('utf-8')
            update = telebot.types.Update.de_json(json_string)

            bot = get_bot_instance(bot_token)
            if bot:
                bot.process_new_updates([update])
                return HttpResponse(status=200)
            else:
                logger.error("Не удалось получить экземпляр бота.")
                return JsonResponse({'status': 'error', 'message': 'Bot instance not available'}, status=500)

        except json.JSONDecodeError:
            logger.error("Некорректный JSON в запросе вебхука.")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке вебхука: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are accepted'}, status=405)


def send_tg_notification_to_user(message, user):
    if not hasattr(user, 'telegram_account'):
        return
    if not user.telegram_account.telegram_id:
        return
    try:
        bot_user = TeleBot(config.TG_TOKEN_USERS)
        bot_user.send_message(user.telegram_account.telegram_id, message)
    except Exception as e:
        logger.info(f"Не получилось отправить сообщение в telegram: {e}")

def _download_from_tg(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{config.TG_TOKEN_USERS}/{file_path}"
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    return r.content