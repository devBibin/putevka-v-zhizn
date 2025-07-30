import json
import telebot
import requests

# Load the bot token from credentials.json
import os
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("TG_TOKEN_ADMIN")
base_url = "http://localhost:8000/bot/"
if not token:
    raise ValueError("Token not found in the credentials file.")

endpoint_url = f"{base_url}{token.replace(':', '')}/"

# Initialize the bot
bot = telebot.TeleBot(token)

# Remove webhook before starting polling
#bot.remove_webhook() 

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handles incoming messages and forwards the entire raw update body to the specified endpoint."""
    try:
        # Reconstruct the `Update` object with `update_id`
        update_object = {
            "update_id": message.json["message_id"],  # Generate update_id from the message_id (or set a custom logic)
            "message": message.json  # Include the entire message object
        }

        raw_message_body = json.dumps(update_object)  # Serialize the `Update` object to JSON 

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
