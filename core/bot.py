import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import sys
import traceback
import telebot
from Putevka import settings

logger = logging.getLogger('django.request')

bot_instances = {}

def get_bot_instance(token):
	if token not in bot_instances:
		try:
			bot_instances[token] = telebot.TeleBot(token, parse_mode='HTML')
		except Exception as e:
			logger.error(f'Невозможно подключиться к телеграмм-боту, {e}')
			return None

		@bot_instances[token].message_handler(commands=['start'])
		def send_welcome(message):
			try:
				bot_instances[token].reply_to(message, f"Привет, {message.from_user.first_name}")
				logger.info(f"Отправлено приветствие пользователю {message.from_user.id}")
			except Exception as e:
				logger.error(f"Ошибка при отправке приветствия: {e}")

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

			bot.process_new_updates([update])

			return HttpResponse(status=200)

		except ValueError as ve:
			logger.error(f"Ошибка токена в вебхуке: {ve}")
			return JsonResponse({'status': 'error', 'message': str(ve)}, status=403)
		except json.JSONDecodeError:
			logger.error("Некорректный JSON в запросе вебхука.")
			return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
		except Exception as e:
			logger.error(f"Критическая ошибка при обработке вебхука: {e}", exc_info=True)
			return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
	else:
		return JsonResponse({'status': 'error', 'message': 'Only POST requests are accepted'}, status=405)