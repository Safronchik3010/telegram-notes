#!/usr/bin/env python3
"""
telegram-notes / fetch.py
Fetches messages from the backend API (no direct Telegram access).
Voice messages are downloaded via backend proxy and transcribed with Whisper.
Classifies messages as IDEA or TASK, appends to ideas.md / tasks.md.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
TASKS_FILE = BASE_DIR / "tasks.md"
IDEAS_FILE = BASE_DIR / "ideas.md"

BACKEND_URL  = os.environ.get(
    "TELEGRAM_NOTES_BACKEND",
    "https://telegram-notes-backend-production.up.railway.app",
).rstrip("/")

# Cursor stored outside the repo so it persists across runs
CURSOR_FILE = Path(os.environ.get("TELEGRAM_NOTES_CURSOR", Path.home() / ".telegram-notes-cursor"))

TASK_KEYWORDS = {
    "сделать", "купить", "написать", "позвонить", "отправить",
    "созвониться", "встретиться", "подготовить", "проверить",
    "напомнить", "todo", "task",
}

# ── Cursor ───────────────────────────────────────────────────────────────────
def load_since_id() -> int:
    if CURSOR_FILE.exists():
        try:
            return int(CURSOR_FILE.read_text().strip())
        except ValueError:
            pass
    return 0

def save_since_id(since_id: int):
    CURSOR_FILE.write_text(str(since_id))

# ── Backend API ───────────────────────────────────────────────────────────────
def fetch_messages(since_id: int) -> list:
    url = f"{BACKEND_URL}/messages?since_id={since_id}&limit=500"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("messages", [])
    except urllib.error.URLError as e:
        raise RuntimeError(f"Backend unavailable ({BACKEND_URL}): {e}")

def download_voice(file_id: str) -> str:
    """Download voice via backend proxy, return path to temp file."""
    url = f"{BACKEND_URL}/voice/{file_id}"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            tmp.write(r.read())
    finally:
        tmp.close()
    return tmp.name

# ── Whisper ───────────────────────────────────────────────────────────────────
def ensure_whisper():
    try:
        import whisper  # noqa
    except ImportError:
        print("Whisper не найден — устанавливаю...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "openai-whisper", "--quiet"]
        )

def transcribe_audio(file_path: str) -> str:
    import whisper
    print(f"  Расшифровываю через Whisper...")
    model = whisper.load_model("base")
    result = model.transcribe(file_path, language=None)
    text = result.get("text", "").strip()
    print(f"  Результат: {text[:80]}{'...' if len(text) > 80 else ''}")
    return text

# ── Classification & formatting ───────────────────────────────────────────────
def is_task(text: str) -> bool:
    words = text.lower().split()
    return any(w in TASK_KEYWORDS for w in words)

def format_entry(text: str, created_at: str, source: str = "text") -> str:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        ts = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        ts = created_at[:16] if created_at else "unknown"
    tag = "🎙️ " if source == "voice" else ""
    return f"- [{ts}] {tag}{text}\n"

def ensure_file(path: Path, header: str):
    if not path.exists():
        path.write_text(f"# {header}\n\n")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ensure_file(TASKS_FILE, "Задачи")
    ensure_file(IDEAS_FILE, "Идеи")

    since_id = load_since_id()
    print(f"Запрашиваю сообщения с id > {since_id}...")

    messages = fetch_messages(since_id)
    print(f"Получено: {len(messages)} сообщений")

    if not messages:
        print("Новых заметок нет.")
        return

    # Pre-check for voice to load Whisper once
    if any(m.get("voice_file_id") for m in messages):
        ensure_whisper()

    n_tasks = 0
    n_ideas = 0
    n_voice = 0
    max_id  = since_id

    for msg in messages:
        msg_id    = msg["id"]
        max_id    = max(max_id, msg_id)
        text      = msg.get("text") or ""
        file_id   = msg.get("voice_file_id")
        created   = msg.get("created_at", "")
        source    = "text"

        # Voice message — download and transcribe
        if file_id and not text:
            print(f"  Голосовое (file_id: {file_id[:20]}...)")
            try:
                tmp_path = download_voice(file_id)
                text     = transcribe_audio(tmp_path)
                source   = "voice"
                n_voice += 1
            except Exception as e:
                print(f"  Ошибка голосового: {e}")
                continue
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        if not text:
            continue

        entry = format_entry(text, created, source)

        if is_task(text):
            with open(TASKS_FILE, "a") as f:
                f.write(entry)
            n_tasks += 1
        else:
            with open(IDEAS_FILE, "a") as f:
                f.write(entry)
            n_ideas += 1

    save_since_id(max_id)

    print(f"\nГотово:")
    print(f"  Задач:  {n_tasks}")
    print(f"  Идей:   {n_ideas}")
    if n_voice:
        print(f"  Голосовых расшифровано: {n_voice}")
    print(f"  Курсор сохранён: {max_id} → {CURSOR_FILE}")


if __name__ == "__main__":
    main()
