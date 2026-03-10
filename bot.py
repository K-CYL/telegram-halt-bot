import os
import time
from collections import Counter
from datetime import datetime

import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
HALTS_URL = "https://raw.githubusercontent.com/K-CYL/nasdaqtrader_halt/main/halts.json"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "K-CYL/nasdaqtrader_halt")
GITHUB_WORKFLOW_ID = os.getenv("GITHUB_WORKFLOW_ID", "update_halt_state.yml")
GITHUB_REF = os.getenv("GITHUB_REF", "main")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")


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


def is_admin_chat(chat_id):
    return str(chat_id) == str(ADMIN_CHAT_ID)


def trigger_github_workflow():
    if not GITHUB_TOKEN:
        return False, "GITHUB_TOKEN 이 설정되지 않았습니다."

    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW_ID}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": GITHUB_REF}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)

        if r.status_code == 204:
            return True, f"GitHub Actions 실행 요청 완료: {GITHUB_REPO} / {GITHUB_WORKFLOW_ID} / ref={GITHUB_REF}"

        try:
            err = r.json()
        except Exception:
            err = r.text

        return False, f"GitHub Actions 실행 실패 ({r.status_code})\n{err}"

    except Exception as e:
        return False, f"GitHub Actions 호출 오류: {e}"


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


def parse_mmddyyyy(date_str):
    raw = normalize_text(date_str)
    if not raw:
        return None

    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def extract_reason_code(reason_text):
    text = normalize_text(reason_text)
    if not text:
        return ""

    if "(" in text and ")" in text:
        left = text.rfind("(")
        right = text.rfind(")")
        if left != -1 and right != -1 and right > left:
            return text[left + 1:right].strip().upper()

    return text.strip().upper()


def has_resume_info(item):
    return bool(
        normalize_text(item.get("resume_date"))
        or normalize_text(item.get("quote_resume_time"))
        or normalize_text(item.get("trade_resume_time"))
    )


def parse_query(text):
    text = normalize_text(text)

    if not text:
        return ("EMPTY", "")

    if text.startswith("/start") or text.startswith("/help"):
        return ("HELP", "")

    if text.startswith("/runhalt"):
        return ("RUNHALT", "")

    if text.startswith("/haltscount"):
        return ("HALTSCOUNT", "")

    if text.startswith("/haltlist"):
        return ("HALTLIST", "")

    if text.startswith("/todayhalt"):
        return ("TODAYHALT", "")

    if text.startswith("/resume"):
        return ("RESUME", "")

    if text.startswith("/topreason"):
        return ("TOPREASON", "")

    if text.lower().startswith("/debughalt"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return ("DEBUGHALT", parts[1].strip())
        return ("DEBUGHALT", "")

    if text.lower().startswith("/reason"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return ("REASON", parts[1].strip())
        return ("REASON", "")

    if text.lower().startswith("/halt"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return ("HALT", parts[1].strip())
        return ("HALT", "")

    if text.startswith("/"):
        return ("UNKNOWN", "")

    return ("SEARCH", text.strip())


def format_halt_message(item):
    symbol = normalize_text(item.get("symbol", "-")) or "-"
    name = normalize_text(item.get("name", "-")) or "-"
    market = normalize_text(item.get("market", "-")) or "-"
    reason = normalize_text(item.get("reason", "-")) or "-"
    halt_date = normalize_text(item.get("date", "-")) or "-"
    halt_time = normalize_text(item.get("time", "-")) or "-"

    lines = [
        "현재 거래정지 상태입니다.",
        "",
        f"종목코드 : {symbol}",
        f"종목명 : {name}",
        f"거래소 : {market}",
        f"정지 사유 : {reason}",
        f"정지일 : {halt_date}",
        f"정지시간 : {halt_time}",
    ]

    if has_resume_info(item):
        resume_date = normalize_text(item.get("resume_date", "-")) or "-"
        quote_resume_time = normalize_text(item.get("quote_resume_time", "-")) or "-"
        trade_resume_time = normalize_text(item.get("trade_resume_time", "-")) or "-"

        lines.append(f"재개일 : {resume_date}")
        lines.append(f"호가재개시간 : {quote_resume_time}")
        lines.append(f"거래재개시간 : {trade_resume_time}")

    return "\n".join(lines)


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
        return "사용법: /debughalt EMPG"

    symbols = [normalize_text(x.get("symbol")) for x in halts]
    exists = any(normalize_text(x.get("symbol")).lower() == q for x in halts)

    preview = ", ".join(symbols[:20]) if symbols else "(없음)"

    return (
        f"조회어: {query}\n"
        f"halts 개수: {len(halts)}\n"
        f"심볼 존재 여부: {'있음' if exists else '없음'}\n"
        f"앞 20개 심볼: {preview}"
    )


def format_halt_list(halts):
    active_items = [x for x in halts if not has_resume_info(x)]

    if not active_items:
        return "현재 거래정지 종목이 없습니다."

    lines = [f"현재 거래정지 종목 ({len(active_items)})", ""]

    for item in active_items:
        symbol = normalize_text(item.get("symbol", "-")) or "-"
        name = normalize_text(item.get("name", "-")) or "-"
        reason = normalize_text(item.get("reason", "-")) or "-"
        lines.append(f"{symbol} - {name} / {reason}")

    text = "\n".join(lines)

    if len(text) > 3500:
        trimmed = [f"현재 거래정지 종목 ({len(active_items)})", ""]
        current_len = len("\n".join(trimmed))

        for item in active_items:
            line = f"{normalize_text(item.get('symbol', '-'))} - {normalize_text(item.get('name', '-'))} / {normalize_text(item.get('reason', '-'))}"
            if current_len + len(line) + 1 > 3500:
                trimmed.append("...")
                trimmed.append("목록이 길어 일부만 표시했습니다.")
                break
            trimmed.append(line)
            current_len += len(line) + 1

        return "\n".join(trimmed)

    return text


def search_by_reason(reason_query, halts):
    rq = normalize_text(reason_query).upper()
    if not rq:
        return []

    matched = []

    for item in halts:
        reason_code = extract_reason_code(item.get("reason"))
        if reason_code == rq:
            matched.append(item)

    return matched


def format_reason_list(reason_code, items):
    rc = normalize_text(reason_code).upper()

    if not rc:
        return "사용법: /reason T12"

    if not items:
        return f"{rc} 코드에 해당하는 RSS 종목이 없습니다."

    lines = [f"{rc} 코드 RSS 종목 ({len(items)})", ""]

    for item in items:
        symbol = normalize_text(item.get("symbol", "-")) or "-"
        name = normalize_text(item.get("name", "-")) or "-"
        market = normalize_text(item.get("market", "-")) or "-"
        reason = normalize_text(item.get("reason", "-")) or "-"
        lines.append(f"{symbol} - {name} / {market} / {reason}")

    text = "\n".join(lines)

    if len(text) > 3500:
        trimmed = [f"{rc} 코드 RSS 종목 ({len(items)})", ""]
        current_len = len("\n".join(trimmed))

        for item in items:
            line = f"{normalize_text(item.get('symbol', '-'))} - {normalize_text(item.get('name', '-'))} / {normalize_text(item.get('market', '-'))} / {normalize_text(item.get('reason', '-'))}"
            if current_len + len(line) + 1 > 3500:
                trimmed.append("...")
                trimmed.append("목록이 길어 일부만 표시했습니다.")
                break
            trimmed.append(line)
            current_len += len(line) + 1

        return "\n".join(trimmed)

    return text


def format_todayhalt(halts):
    if not halts:
        return "RSS 종목이 없습니다."

    dates = [parse_mmddyyyy(x.get("date")) for x in halts]
    dates = [d for d in dates if d is not None]

    if not dates:
        return "날짜 정보가 없습니다."

    latest_date = max(dates)
    items = [
        x for x in halts
        if parse_mmddyyyy(x.get("date")) == latest_date and not has_resume_info(x)
    ]

    if not items:
        return f"오늘({latest_date.strftime('%m/%d/%Y')}) 발생한 현재 거래정지 종목이 없습니다."

    lines = [f"오늘 발생한 halt ({latest_date.strftime('%m/%d/%Y')}) / {len(items)}", ""]

    for item in items:
        symbol = normalize_text(item.get("symbol", "-")) or "-"
        name = normalize_text(item.get("name", "-")) or "-"
        reason = normalize_text(item.get("reason", "-")) or "-"
        halt_time = normalize_text(item.get("time", "-")) or "-"
        lines.append(f"{symbol} - {name} / {reason} / {halt_time}")

    return "\n".join(lines)


def format_resume_list(halts):
    items = [x for x in halts if has_resume_info(x)]

    if not items:
        return "재개 정보가 있는 종목이 없습니다."

    items.sort(key=lambda x: (normalize_text(x.get("resume_date")), normalize_text(x.get("symbol"))))

    lines = [f"재개 예정/재개 정보 종목 ({len(items)})", ""]

    for item in items:
        symbol = normalize_text(item.get("symbol", "-")) or "-"
        name = normalize_text(item.get("name", "-")) or "-"
        resume_date = normalize_text(item.get("resume_date", "-")) or "-"
        quote_resume_time = normalize_text(item.get("quote_resume_time", "-")) or "-"
        trade_resume_time = normalize_text(item.get("trade_resume_time", "-")) or "-"
        lines.append(
            f"{symbol} - {name} / 재개일 {resume_date} / 호가 {quote_resume_time} / 거래 {trade_resume_time}"
        )

    text = "\n".join(lines)

    if len(text) > 3500:
        trimmed = [f"재개 예정/재개 정보 종목 ({len(items)})", ""]
        current_len = len("\n".join(trimmed))

        for item in items:
            line = (
                f"{normalize_text(item.get('symbol', '-'))} - "
                f"{normalize_text(item.get('name', '-'))} / "
                f"재개일 {normalize_text(item.get('resume_date', '-'))} / "
                f"호가 {normalize_text(item.get('quote_resume_time', '-'))} / "
                f"거래 {normalize_text(item.get('trade_resume_time', '-'))}"
            )
            if current_len + len(line) + 1 > 3500:
                trimmed.append("...")
                trimmed.append("목록이 길어 일부만 표시했습니다.")
                break
            trimmed.append(line)
            current_len += len(line) + 1

        return "\n".join(trimmed)

    return text


def format_topreason(halts):
    if not halts:
        return "RSS 종목이 없습니다."

    counter = Counter()

    for item in halts:
        reason_code = extract_reason_code(item.get("reason"))
        if reason_code:
            counter[reason_code] += 1

    if not counter:
        return "정지 사유 통계가 없습니다."

    lines = ["현재 RSS 종목 사유 통계", ""]

    for code, count in counter.most_common():
        lines.append(f"{code} : {count}")

    return "\n".join(lines)


def extract_message(update):
    if "message" in update:
        return update["message"]
    if "channel_post" in update:
        return update["channel_post"]
    return None


def handle_text(text, chat_id=None):
    command, value = parse_query(text)

    if command == "RUNHALT":
        ok, msg = trigger_github_workflow()
        return msg

    halts = load_halts()

    if command == "HELP":
        return (
            "사용 방법\n\n"
            "종목코드 또는 종목명을 입력하면 RSS 기준 거래정지 종목 여부를 알려드립니다.\n\n"
            "샘플 검색:\n"
            "EMPG\n"
            "/halt EMPG\n\n"
            "명령어:\n"
            "/runhalt - GitHub Actions 강제 실행\n"
            "/haltlist - 현재 거래정지 종목 목록\n"
            "/todayhalt - 오늘 발생한 halt\n"
            "/resume - 재개 예정/재개 정보 종목\n"
            "/reason T12 - 사유 코드별 검색\n"
            "/topreason - halt 사유 통계\n"
            "/haltscount - 현재 저장 종목 수 확인\n"
            "/debughalt EMPG - 특정 종목 디버그\n"
        )

    if command == "HALTSCOUNT":
        symbols = [normalize_text(x.get("symbol")) for x in halts[:20]]
        preview = ", ".join(symbols) if symbols else "(없음)"
        return f"현재 halts 개수: {len(halts)}\n앞 20개 심볼: {preview}"

    if command == "HALTLIST":
        return format_halt_list(halts)

    if command == "TODAYHALT":
        return format_todayhalt(halts)

    if command == "RESUME":
        return format_resume_list(halts)

    if command == "TOPREASON":
        return format_topreason(halts)

    if command == "DEBUGHALT":
        return debug_halt(value, halts)

    if command == "REASON":
        matched = search_by_reason(value, halts)
        return format_reason_list(value, matched)

    if command in ("HALT", "SEARCH"):
        item = search_halt(value, halts)
        if item:
            return format_halt_message(item)
        return "현재 거래정지 종목이 아닙니다."

    if command == "UNKNOWN":
        return None

    return None


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
                print(f"chat_id={chat_id}", flush=True)

                reply = handle_text(text, chat_id=chat_id)
                if not reply:
                    continue

                send_message(chat_id, reply, reply_to_message_id=message_id)

        except Exception as e:
            print(f"Error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()