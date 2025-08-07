from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import sys
import traceback
import telebot

import config
from Putevka import settings

bot = telebot.TeleBot(config.TG_TOKEN_ADMIN)

@csrf_exempt
def webhook(request, code):
	try:
		json_string = request.body.decode("utf-8")
		update = telebot.types.Update.de_json(json_string)
		
		if code == config.TG_TOKEN_ADMIN.replace(":", ""):
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
