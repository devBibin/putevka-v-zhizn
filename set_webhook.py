from bot import bot
import os
from dotenv import load_dotenv

load_dotenv()
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot.remove_webhook()
bot.set_webhook("https://6377076e8be6.ngrok-free.app/telegram/webhook/")

print(f"Webhook set to {WEBHOOK_URL}")