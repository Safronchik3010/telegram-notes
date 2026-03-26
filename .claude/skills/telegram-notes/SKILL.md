---
name: telegram-notes
description: "Fetch text and voice messages from Telegram bot, transcribe voice via local Whisper, classify as ideas or tasks, save to telegram-notes/ideas.md and telegram-notes/tasks.md. Uses .last_update_id to avoid duplicate processing."
---

You are running the telegram-notes pipeline. Follow these steps exactly:

## Цикл: ВЗЯТЬ → ОБРАБОТАТЬ → ПОЛОЖИТЬ

### 1. ВЗЯТЬ (fetch)
- Read `.last_update_id` file — if it exists, use its value as offset+1 so Telegram only returns NEW messages (update_id > last saved).
- If `.last_update_id` does not exist, fetch all messages (offset=0).
- Call Telegram Bot API `getUpdates?offset=<offset>` to get only unprocessed messages.

### 2. ОБРАБОТАТЬ (transcribe + classify)
- For **text messages**: classify directly.
- For **voice messages**: download the audio file from Telegram, transcribe it locally using Whisper (`whisper` Python package, model=base). If Whisper is not installed, install it first with pip. If ffmpeg is missing, install it.
- Classify each message as **идея** (idea) or **задача** (task) based on keywords.

### 3. ПОЛОЖИТЬ (save)
- Append ideas to `ideas.md` with timestamp.
- Append tasks to `tasks.md` with timestamp.
- After all messages are processed, save the highest `update_id` seen to `.last_update_id` file — this prevents duplicate processing on the next run.

## Запуск

Run the script:
```bash
cd ~/datapeople/telegram-notes && python3 fetch.py
```

Report: how many voice messages were transcribed, how many ideas and tasks were saved, and confirm that `.last_update_id` was updated.
