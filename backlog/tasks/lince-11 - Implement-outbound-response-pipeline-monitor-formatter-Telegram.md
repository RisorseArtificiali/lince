---
id: LINCE-11
title: Implement outbound response pipeline (monitor -> formatter -> Telegram)
status: To Do
assignee: []
created_date: '2026-03-03 14:33'
updated_date: '2026-03-03 16:51'
labels:
  - telebridge
  - integration
milestone: m-7
dependencies:
  - LINCE-7
  - LINCE-8
  - LINCE-9
  - LINCE-10
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wire together the JSONL session monitor, transcript parser, and response formatter into a working outbound pipeline that delivers Claude Code responses to Telegram.

**Pipeline flow:**
```
SessionMonitor (new JSONL entries)
    -> TranscriptParser.parse_entries()
    -> ResponseFormatter.format_entries() + to_telegram_markdown() + split_message()
    -> bot.send_message() to the correct Telegram chat/topic
```

**Callback wiring:**
- SessionMonitor calls `await message_callback(session_id, raw_entries)`
- Callback function in bot.py:
  1. Parse entries with TranscriptParser
  2. Format with ResponseFormatter
  3. Determine target Telegram chat_id and thread_id from session mapping
  4. Send each message part via Telegram API
  5. Handle MarkdownV2 failures with plaintext fallback

**Message sending with fallback:**
```python
async def send_response(bot, chat_id, text, thread_id=None):
    try:
        md_text = to_telegram_markdown(text)
        parts = split_message(md_text)
        for part in parts:
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode="MarkdownV2",
                message_thread_id=thread_id,
                disable_web_page_preview=True,
            )
    except TelegramError:
        # Fallback: strip formatting, send as plain text
        parts = split_message(strip_sentinels(text))
        for part in parts:
            await bot.send_message(chat_id=chat_id, text=part, message_thread_id=thread_id)
```

**For MVP**: Single session mapping (one hardcoded chat_id from config or first message). Multi-session topic mapping comes in the Sessions milestone.

**Image handling**: If ParsedEntry has image_data, send as photo via `bot.send_photo()` instead of text.

**This task is the integration glue** — it connects the independently-built monitor, parser, and formatter into a working end-to-end flow. After this task, the MVP is functionally complete: send text from Telegram, receive formatted responses back.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Monitor callback wired to parser and formatter
- [ ] #2 Formatted responses sent to correct Telegram chat
- [ ] #3 MarkdownV2 fallback to plain text on parse errors
- [ ] #4 Image entries sent as photos
- [ ] #5 End-to-end flow works: send text from Telegram -> receive Claude response on Telegram
- [ ] #6 Errors logged but don't crash the pipeline
<!-- AC:END -->
