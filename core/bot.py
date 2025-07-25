from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import sys
import traceback
import telebot
from Putevka import settings
from django.http import JsonResponse
import json

from users.models import TelegramAccount, User

@csrf_exempt
def telegram_webhook(request):
    if request.method == "POST":
        data = json.loads(request.body)
        message = data.get("message")
        if not message:
            return JsonResponse({"ok": True})

        chat = message.get("chat", {})
        text = message.get("text", "")
        telegram_id = chat.get("id")
        username = chat.get("username")
        first_name = chat.get("first_name")
        last_name = chat.get("last_name")

        if text.startswith("/start"):
            try:
                _, secret_code = text.split()
                user = User.objects.get(telegram_account__secret_code=secret_code)
                TelegramAccount.objects.update_or_create(
                    user=user,
                    defaults={
                        "telegram_id": telegram_id,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    }
                )
                send_message(telegram_id, "✅ Успешно привязано к аккаунту!")
            except Exception as e:
                send_message(telegram_id, "❌ Ошибка привязки. Неверный код или пользователь не найден.")

        return JsonResponse({"ok": True})

bot = telebot.TeleBot(settings.TG_TOKEN)

@csrf_exempt
def webhook(request, code):
	try:
		json_string = request.body.decode("utf-8")
		update = telebot.types.Update.de_json(json_string)
		
		if code == settings.TG_TOKEN.replace(":", ""):
			bot.process_new_updates([update])

		# Return immediately after starting the background thread
		return HttpResponse(status=200)
	
	except Exception as e:
		type, value, tb = sys.exc_info()
		
		# Log exception details
		print(sys.exc_info())
		print(traceback.format_tb(tb))

		return HttpResponse(status=200)

@bot.message_handler(commands=['start'])
def echo(message):
	bot.reply_to(message, "Hello")
