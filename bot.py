import os
import json
import time
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# GitHub raw URL
HALTS_URL = "https://raw.githubusercontent.com/K-CYL/telegram-halt-bot/main/halts.json"


def get_updates(offset=None, timeout=30):
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    r = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=timeout + 10)
    r.raise_for_status()
    return r.json()


def send_message(chat_id, text, reply_to_message_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    r = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def load_halts():
    try:
        r = requests.get(HALTS_URL, timeout=20)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list):
            print(f"halts loaded from github: {len(data)} items", flush=True)
            return data

        print("halts.json from github is not a list", flush=True)
        return []

    except Exception as e:
        print(f"load_halts error: {e}", flush=True)
        return []


def normalize_text(value):
    return str(value or "").strip()


def parse_query(text):
    text = normalize_text(text)

    if not text:
        return ""

    if text.lower().startswith("/halt"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1].strip()
        return ""

    if text.startswith("/start") or text.startswith("/help"):
        return "__HELP__"

    if text.startswith("/haltscount"):
        return "__HALTSCOUNT__"

    if text.lower().startswith("/debughalt"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return f"__DEBUGHALT__::{parts[1].strip()}"
        return "__DEBUGHALT__::"

    if text.startswith("/"):
        return ""

    return text.strip()


def format_halt_message(item):
    symbol = normalize_text(item.get("symbol", "-")) or "-"
    name = normalize_text(item.get("name", "-")) or "-"
    market = normalize_text(item.get("market", "-")) or "-"
    reason = normalize_text(item.get("reason", "-")) or "-"
    halt_date = normalize_text(item.get("date", "-")) or "-"
    halt_time = normalize_text(item.get("time", "-")) or "-"

    return (
        "현재 거래정지 상태입니다.\n\n"
        f"종목코드 : {symbol}\n"
        f"종목명 : {name}\n"
        f"거래소 : {market}\n"
        f"정지 사유 : {reason}\n"
        f"정지일 : {halt_date}\n"
        f"정지시간 : {halt_time}"
    )


def search_halt(query, halts):
    q = normalize_text(query).lower()
    if not q:
        return None

    for item in halts:
        symbol = normalize_text(item.get("symbol")).lower()
        if symbol == q:
            return item

    for item in halts:
        name = normalize_text(item.get("name")).lower()
        if name == q:
            return item

    for item in halts:
        name = normalize_text(item.get("name")).lower()
        if q in name:
            return item

    return None


def debug_halt(query, halts):
    q = normalize_text(query).lower()
    if not q:
        return "사용법: /debughalt IMMP"

    symbols = [normalize_text(x.get("symbol")) for x in halts]
    exists = any(normalize_text(x.get("symbol")).lower() == q for x in halts)

    preview = ", ".join(symbols[:20]) if symbols else "(없음)"

    return (
        f"조회어: {query}\n"
        f"halts 개수: {len(halts)}\n"
        f"심볼 존재 여부: {'있음' if exists else '없음'}\n"
        f"앞 20개 심볼: {preview}"
    )


def extract_message(update):
    if "message" in update:
        return update["message"]
    if "channel_post" in update:
        return update["channel_post"]
    return None


def handle_text(text):
    query = parse_query(text)
    halts = load_halts()

    if query == "__HELP__":
        return (
            "사용 방법\n\n"
            "종목코드 또는 종목명을 입력하면 현재 거래정지 여부를 알려드립니다.\n\n"
            "예시:\n"
            "IMMP\n"
            "/halt IMMP\n\n"
            "디버그:\n"
            "/haltscount\n"
            "/debughalt IMMP"
        )

    if query == "__HALTSCOUNT__":
        symbols = [normalize_text(x.get("symbol")) for x in halts[:20]]
        preview = ", ".join(symbols) if symbols else "(없음)"
        return f"현재 halts 개수: {len(halts)}\n앞 20개 심볼: {preview}"

    if query.startswith("__DEBUGHALT__::"):
        raw = query.split("::", 1)[1]
        return debug_halt(raw, halts)

    if not query:
        return None

    item = search_halt(query, halts)

    if item:
        return format_halt_message(item)

    return "현재 거래정지 종목이 아닙니다."


def main():
    print("Bot started.", flush=True)
    offset = None

    while True:
        try:
            data = get_updates(offset=offset, timeout=30)

            if not data.get("ok"):
                print(f"Telegram API error: {data}", flush=True)
                time.sleep(3)
                continue

            results = data.get("result", [])

            for update in results:
                offset = update["update_id"] + 1

                message = extract_message(update)
                if not message:
                    continue

                chat = message.get("chat", {})
                chat_id = chat.get("id")
                message_id = message.get("message_id")
                text = message.get("text", "")

                if not chat_id or not text:
                    continue

                print(f"received text: {text}", flush=True)

                reply = handle_text(text)
                if not reply:
                    continue

                send_message(chat_id, reply, reply_to_message_id=message_id)

        except Exception as e:
            print(f"Error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()