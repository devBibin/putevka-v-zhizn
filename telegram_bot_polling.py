import json
import telebot
import requests
import os
from flask import Flask, request

from dotenv import load_dotenv
load_dotenv()

token = os.getenv("TG_TOKEN")
base_url = "http://localhost:8000/bot/"
if not token:
    raise ValueError("Token not found in the credentials file.")

endpoint_url = f"{base_url}{token.replace(':', '')}/"

bot = telebot.TeleBot(token)
app = Flask(__name__)

@app.route('/' + token, methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Failed to process update: {e}")
    return '', 200

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        update_object = {
            "update_id": message.message_id,  # Лучше использовать message.message_id
            "message": message.json  # Вся информация сообщения
        }
        raw_message_body = json.dumps(update_object)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(endpoint_url, data=raw_message_body, headers=headers)
        print("Sent to endpoint")
        if response.status_code != 200:
            bot.reply_to(message, f"Failed to process message. Error: {response.status_code}")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

if __name__ == '__main__':
    # Удаляем старый вебхук, если есть, и ставим новый
    bot.remove_webhook()
    WEBHOOK_URL = f"https://yourdomain.com/{token}"  # Замените на свой публичный HTTPS URL
    bot.set_webhook(url=WEBHOOK_URL)

    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=5000)
