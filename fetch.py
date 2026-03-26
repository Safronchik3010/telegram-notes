#!/usr/bin/env python3
"""
telegram-notes / fetch.py
Fetches text messages from Telegram bot, classifies as IDEA or TASK,
appends to ideas.md / tasks.md, saves offset.
"""

import os
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
TASKS_FILE = BASE_DIR / "tasks.md"
IDEAS_FILE  = BASE_DIR / "ideas.md"
OFFSET_FILE = BASE_DIR / ".offset"

TASK_KEYWORDS = {
    "сделать", "купить", "написать", "позвонить", "отправить",
    "созвониться", "встретиться", "подготовить", "проверить",
    "напомнить", "todo", "task",
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")
    return token

def load_offset() -> int:
    if OFFSET_FILE.exists():
        return int(OFFSET_FILE.read_text().strip())
    return 0

def save_offset(offset: int):
    OFFSET_FILE.write_text(str(offset))

def fetch_updates(token: str, offset: int) -> list:
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=5"
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data["result"]

def is_task(text: str) -> bool:
    words = text.lower().split()
    return any(w in TASK_KEYWORDS for w in words)

def format_entry(text: str, ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"- [{dt}] {text}\n"

def ensure_file(path: Path, header: str):
    if not path.exists():
        path.write_text(f"# {header}\n\n")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    ensure_file(TASKS_FILE, "Задачи")
    ensure_file(IDEAS_FILE,  "Идеи")

    token   = get_token()
    offset  = load_offset()
    updates = fetch_updates(token, offset)

    n_tasks = 0
    n_ideas = 0
    max_update_id = offset - 1

    for upd in updates:
        update_id = upd["update_id"]
        max_update_id = max(max_update_id, update_id)

        msg = upd.get("message") or upd.get("channel_post")
        if not msg:
            continue
        text = msg.get("text")
        if not text:
            continue  # skip voice, photo, stickers, etc.

        ts    = msg.get("date", 0)
        entry = format_entry(text, ts)

        if is_task(text):
            with open(TASKS_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            n_tasks += 1
        else:
            with open(IDEAS_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            n_ideas += 1

    if updates:
        save_offset(max_update_id + 1)

    print(f"✅ Обработано обновлений: {len(updates)}")
    print(f"   📋 Задач добавлено:  {n_tasks}")
    print(f"   💡 Идей добавлено:   {n_ideas}")
    return n_tasks, n_ideas

if __name__ == "__main__":
    main()
