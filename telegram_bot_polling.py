import json
import logging

import telebot
import requests
import config

from dotenv import load_dotenv

import config

load_dotenv()


logger = logging.getLogger(__name__)

token = config.TG_TOKEN_USERS

base_url = f"{config.BASE_URL}/bot/"
if not token:
    raise ValueError("Token not found in the credentials file.")

endpoint_url = f"{base_url}{token}/"

bot = telebot.TeleBot(token)

bot.remove_webhook()

@bot.message_handler(func=lambda message: True, content_types=['text', 'contact'])
def handle_message(message):
    try:
        update_object = {
            "update_id": message.json["message_id"],
            "message": message.json
        }

        raw_message_body = json.dumps(update_object)

        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.post(endpoint_url, data=raw_message_body, headers=headers)
        print("Sent to endpoint")
        
        if response.status_code != 200:
            bot.reply_to(message, f"Failed to process message. Error: {response.status_code}")
    
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

if __name__ == "__main__":
    print("Bot is polling...")
    bot.infinity_polling()
