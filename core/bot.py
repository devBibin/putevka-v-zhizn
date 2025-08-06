import telebot
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TG_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN)

# === Обработка команды /start с секретной строкой ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Ошибка: отсутствует секретная строка.")
        return

    secret = args[1]

    payload = {
        "telegram_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "secret": secret
    }

    # URL backend'а, куда передаётся связка аккаунтов
    BACKEND_URL = os.getenv("BACKEND_URL")  # Например: http://localhost:8000/api/telegram/link

    try:
        response = requests.post(BACKEND_URL, json=payload)
        if response.status_code == 200:
            bot.send_message(message.chat.id, "Аккаунт успешно связан.")
        else:
            bot.send_message(message.chat.id, f"Ошибка при связывании: {response.status_code}")
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")


# === Установка вебхука при старте ===
# bot.remove_webhook()
# bot.set_webhook(url="https://bd9cb187354d.ngrok-free.app/telegram/webhook/")

# # === Поддерживаем процесс живым (бот работает и ждёт запросы от Telegram через вебхук) ===
# import time
# print("Bot is running with webhook...")
# while True:
#     time.sleep(10)
