---
id: LINCE-20
title: Implement Telegram voice message handler with VoxCode Transcriber
status: To Do
assignee: []
created_date: '2026-03-03 14:35'
labels:
  - telebridge
  - voice
milestone: m-5
dependencies:
  - LINCE-10
  - LINCE-19
references:
  - voxcode/src/voxcode/transcriber.py
  - Transcriber.transcribe() API
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/handlers/voice.py` — handles Telegram voice messages by downloading, converting, transcribing with VoxCode's Whisper engine, and forwarding text to Claude Code.

**End-to-end flow:**
```
Telegram voice message (OGG/Opus)
    -> Download via Telegram API
    -> ogg_to_numpy() conversion (LINCE-19)
    -> VoxCode Transcriber.transcribe(audio_array, language)
    -> bridge.send_text(transcribed_text)
    -> Reply to user: "🎤 Trascritto: {text}"
```

**Implementation:**
```python
async def handle_voice(update: Update, context: CallbackContext):
    # 1. Auth check
    if not is_user_allowed(update.effective_user.id):
        return
    
    # 2. Check voice feature enabled
    if not config.voice.enabled:
        await update.message.reply_text("Voice messages disabled in config")
        return
    
    # 3. Download voice file
    voice_file = await update.message.voice.get_file()
    ogg_bytes = await voice_file.download_as_bytearray()
    
    # 4. Convert OGG -> numpy
    audio_array = await ogg_to_numpy(bytes(ogg_bytes))
    
    # 5. Transcribe (run in thread pool — Whisper is CPU/GPU intensive)
    transcriber = get_transcriber()  # singleton, lazy-loaded
    result = await asyncio.to_thread(
        transcriber.transcribe, audio_array, config.voice.language
    )
    
    # 6. Check for empty transcription
    if not result.text.strip():
        await update.message.reply_text("Could not transcribe audio")
        return
    
    # 7. Send to Claude Code
    bridge.send_text(result.text)
    
    # 8. Confirm to user
    await update.message.reply_text(f"🎤 {result.text}")
```

**Transcriber singleton management:**
- Lazy-load on first voice message (Whisper model loading takes seconds)
- Configure from `config.voice`: model, device, compute_type
- Import `Transcriber` from `voxcode.transcriber`
- Run transcription in `asyncio.to_thread()` to avoid blocking event loop

**VoxCode dependency:**
- `telebridge` depends on `voxcode` package (the transcriber module)
- In pyproject.toml: `voxcode` as optional dependency in `[voice]` group
- Or: extract Transcriber to shared package if preferred

**Duration limit**: Telegram voice messages can be long. Consider a configurable max duration (e.g., 120 seconds) — reject longer messages to avoid GPU/CPU overload.

**Language**: Use `config.voice.language` (default "auto" for auto-detect). Same parameter as VoxCode.

**Also handle video notes and audio messages**: Telegram has voice messages (.ogg), audio messages (.mp3/.m4a), and video notes (round videos). For MVP, only voice messages. Audio messages can reuse same handler with different download path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Downloads Telegram voice message OGG file
- [ ] #2 Converts to numpy via ogg_to_numpy()
- [ ] #3 Transcribes via VoxCode Transcriber (lazy-loaded singleton)
- [ ] #4 Transcription runs in thread pool (non-blocking)
- [ ] #5 Transcribed text sent to Claude Code via bridge.send_text()
- [ ] #6 Confirmation with transcribed text sent to user
- [ ] #7 Empty transcriptions handled gracefully
- [ ] #8 Voice feature toggleable via config
- [ ] #9 Language configurable (auto, it, en, etc.)
<!-- AC:END -->
