import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import telebot
from core.models import TelegramAccount, RegistrationPersonalData, UserInfo
import config

logger = logging.getLogger('django.request')

bot_instances = {}

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
							bot_instances[token].send_message(message.chat.id,
															  "Ваш аккаунт Telegram уже привязан и веб-аккаунт активирован!")
							return

						if telegram_account.telegram_id and str(telegram_account.telegram_id) != str(message.chat.id):
							bot_instances[token].send_message(message.chat.id,
															  "Этот токен активации привязан к другому Telegram-аккаунту, либо уже был использован.")
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

						bot_instances[token].send_message(message.chat.id,
														  f"Привет, {telegram_account.user.username}! Для активации аккаунта на сайте, пожалуйста, поделитесь своим номером телефона.",
														  reply_markup=markup)

						logger.info(
							f"Запрошен номер телефона для активации токена {activation_token_str} для пользователя {telegram_account.user.username}")

					except TelegramAccount.DoesNotExist:
						bot_instances[token].send_message(message.chat.id, "Неверный токен активации.")
						logger.warning(
							f"Неверный токен активации от Telegram ID {message.chat.id}: {activation_token_str}")
					except Exception as e:
						logger.error(f"Ошибка в handle_start с токеном: {e}", exc_info=True)
						bot_instances[token].send_message(message.chat.id,
														  "Произошла ошибка при обработке вашего запроса.")
				else:
					bot_instances[token].send_message(message.chat.id, "Неизвестная команда /start.")
			else:
				bot_instances[token].send_message(message.chat.id,
												  "Привет! Чтобы активировать аккаунт, перейдите по ссылке с сайта.")

		@bot_instances[token].message_handler(content_types=['contact'])
		def handle_contact(message):
			if message.contact is not None:
				telegram_id = str(message.from_user.id)
				phone_number = message.contact.phone_number

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

					user = UserInfo.objects.filter(phone_number=phone_number).first()

					if user:
						bot_instances[token].send_message(message.chat.id,
														  f'Этот номер телефона уже зарегистрирован.')
						return None

					if attempt:
						attempt.phone_number = phone_number
						attempt.user.user_info.phone_number = phone_number
						attempt.user.user_info.save()
						attempt.phone_verified = True
						attempt.current_step = 'finish'
						attempt.save()

					bot_instances[token].send_message(message.chat.id,
													  f"Поздравляем, {telegram_account.user.username}! Ваш Telegram-аккаунт успешно привязан, и ваш веб-аккаунт активирован! Теперь вы можете вернуться на сайт и завершить регистрацию.",
													  reply_markup=telebot.types.ReplyKeyboardRemove())
					logger.info(
						f"Аккаунт пользователя {telegram_account.user.username} успешно активирован через Telegram ID {telegram_id}.")

				except TelegramAccount.DoesNotExist:
					bot_instances[token].send_message(message.chat.id,
													  "Не удалось найти аккаунт, ожидающий активации для этого Telegram ID. Пожалуйста, убедитесь, что вы нажали ссылку активации на сайте и поделились своим номером с того же аккаунта Telegram.")
					logger.warning(f"Не удалось найти профиль для активации от Telegram ID {telegram_id}.")
				except Exception as e:
					logger.error(f"Ошибка при обработке контакта: {e}", exc_info=True)
					bot_instances[token].send_message(message.chat.id,
													  "Произошла ошибка при привязке вашего номера. Пожалуйста, попробуйте еще раз.")
			else:
				bot_instances[token].send_message(message.chat.id, "Вы не поделились номером телефона.")

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
