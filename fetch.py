#!/usr/bin/env python3
"""
telegram-notes / fetch.py
Fetches text AND voice messages from Telegram bot.
Voice messages are transcribed locally via Whisper.
Classifies messages as IDEA or TASK, appends to ideas.md / tasks.md.
"""

import os
import json
import sys
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
TASKS_FILE  = BASE_DIR / "tasks.md"
IDEAS_FILE  = BASE_DIR / "ideas.md"
OFFSET_FILE = BASE_DIR / ".offset"

TASK_KEYWORDS = {
    "сделать", "купить", "написать", "позвонить", "отправить",
    "созвониться", "встретиться", "подготовить", "проверить",
    "напомнить", "todo", "task",
}

# ── Whisper setup ────────────────────────────────────────────────────────────
def ensure_whisper():
    """Install openai-whisper locally if not available."""
    try:
        import whisper  # noqa
        return True
    except ImportError:
        print("⏳ Whisper не найден — устанавливаю локально...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "openai-whisper", "--quiet"]
        )
        print("✅ Whisper установлен.")
        return True

def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file using local Whisper model."""
    import whisper
    print(f"🎙️  Расшифровываю аудио через Whisper (может занять ~1 мин при первом запуске)...")
    model = whisper.load_model("base")
    result = model.transcribe(file_path, language=None)  # auto-detect language
    text = result.get("text", "").strip()
    print(f"📝 Расшифровано: {text[:80]}{'...' if len(text) > 80 else ''}")
    return text

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
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data["result"]

def download_voice(token: str, file_id: str) -> str:
    """Download voice message, return path to temp .ogg file."""
    # Step 1: get file path
    url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    with urllib.request.urlopen(url, timeout=10) as r:
        info = json.loads(r.read())
    file_path = info["result"]["file_path"]

    # Step 2: download file to temp location
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    suffix = Path(file_path).suffix or ".ogg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with urllib.request.urlopen(download_url, timeout=30) as r:
        tmp.write(r.read())
    tmp.close()
    return tmp.name

def is_task(text: str) -> bool:
    words = text.lower().split()
    return any(w in TASK_KEYWORDS for w in words)

def format_entry(text: str, ts: int, source: str = "text") -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    tag = "🎙️ " if source == "voice" else ""
    return f"- [{dt}] {tag}{text}\n"

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

    n_tasks  = 0
    n_ideas  = 0
    n_voice  = 0
    n_skip   = 0
    max_update_id = offset - 1

    # Ensure Whisper is available before processing any voice messages
    has_voice = any(
        (upd.get("message") or upd.get("channel_post") or {}).get("voice")
        for upd in updates
    )
    if has_voice:
        ensure_whisper()

    for upd in updates:
        update_id = upd["update_id"]
        max_update_id = max(max_update_id, update_id)

        msg = upd.get("message") or upd.get("channel_post")
        if not msg:
            continue

        ts     = msg.get("date", 0)
        text   = None
        source = "text"

        # ── Text message ────────────────────────────────────────────────────
        if msg.get("text"):
            text = msg["text"]

        # ── Voice message ────────────────────────────────────────────────────
        elif msg.get("voice"):
            voice    = msg["voice"]
            file_id  = voice["file_id"]
            print(f"🎙️  Голосовое сообщение (file_id: {file_id[:20]}...)")
            try:
                tmp_path = download_voice(token, file_id)
                text     = transcribe_audio(tmp_path)
                source   = "voice"
                n_voice += 1
            except Exception as e:
                print(f"⚠️  Не удалось расшифровать голосовое: {e}")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        # ── Other types (photo, sticker, etc.) ──────────────────────────────
        else:
            n_skip += 1
            continue

        if not text:
            n_skip += 1
            continue

        entry = format_entry(text, ts, source)

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

    print(f"\n✅ Обработано обновлений: {len(updates)}")
    print(f"   🎙️  Голосовых расшифровано: {n_voice}")
    print(f"   📋 Задач добавлено:         {n_tasks}")
    print(f"   💡 Идей добавлено:          {n_ideas}")
    if n_skip:
        print(f"   ⏭️  Пропущено (фото/стикеры): {n_skip}")
    return n_tasks, n_ideas

if __name__ == "__main__":
    main()
