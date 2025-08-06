import json
import telebot
import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TG_TOKEN")
base_url = "http://localhost:8000/bot/"
if not token:
    raise ValueError("Token not found")

# Удаляем двоеточия из токена для URL
token_url = token.replace(":", "")
endpoint_url = f"{base_url}{token_url}/"

bot = telebot.TeleBot(token)
bot.remove_webhook()

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        update_object = {
            "update_id": message.message_id,  # message_id используем для update_id
            "message": message.json  # полное сообщение
        }
        raw_body = json.dumps(update_object)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(endpoint_url, data=raw_body, headers=headers)
        print("Sent to endpoint")

        if response.status_code != 200:
            bot.reply_to(message, f"Ошибка обработки: {response.status_code}")

    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {e}")

if __name__ == "__main__":
    print("Бот запущен и работает на polling...")
    bot.infinity_polling()