from fastapi import FastAPI, Request
import telebot
import os
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TG_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = FastAPI()

@app.post(f"/bot/{TOKEN.replace(':', '')}/")
async def telegram_webhook(request: Request):
    body = await request.body()
    update = telebot.types.Update.de_json(json.loads(body), bot)
    bot.process_new_updates([update])
    return {"status": "ok"}