import os
import requests
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

def send_message(chat_id, text, reply_to_message_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    r = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=20)
    r.raise_for_status()


@app.route("/", methods=["GET"])
def home():
    return "telegram-halt-bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    message = data.get("message") or data.get("channel_post")
    if not message:
        return "ok", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return "ok", 200

    if text == "/start":
        reply = (
            "봇 정상 작동중입니다.\n\n"
            "명령어:\n"
            "/start\n"
            "/help\n"
            "/runhalt"
        )
    elif text == "/help":
        reply = (
            "사용 방법\n\n"
            "/runhalt : GitHub Actions 실행\n"
            "종목코드 조회 기능은 다음 단계에서 추가 가능"
        )
    elif text == "/runhalt":
        reply = "runhalt 요청을 받았습니다."
    else:
        reply = f"입력값: {text}"

    send_message(chat_id, reply, reply_to_message_id=message_id)
    return "ok", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
