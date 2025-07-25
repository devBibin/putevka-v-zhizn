from flask import Flask, request

app = Flask(__name__)

@app.route("/bot/7678271485AAE8uawzz1a43dzRlo7c06Tqz73WPOI90eU/", methods=["POST"])
def webhook():
    data = request.json
    print("Получено сообщение:", data)
    # Тут можно добавить обработку сообщения
    
    return '', 200  # Отвечаем Telegram, что приняли данные успешно

if __name__ == "__main__":
    app.run(port=5001)