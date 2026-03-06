---
id: LINCE-18
title: Implement Telegram photo forwarding to Claude Code
status: To Do
assignee: []
created_date: '2026-03-03 14:35'
labels:
  - telebridge
  - media
milestone: m-4
dependencies:
  - LINCE-12
  - LINCE-10
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/handlers/media.py` — handles photos sent from Telegram and forwards them to Claude Code.

**Flow:**
1. User sends photo in Telegram topic
2. Bot downloads photo via `message.photo[-1].get_file()` (highest resolution)
3. Save to temporary location in the session's cwd (or a dedicated temp dir)
4. Send the file path to Claude Code via `bridge.send_text(f"/path/to/image.jpg")`
   - Claude Code can read images when given a path
5. Reply to user confirming receipt: "Image received: filename.jpg"

**Implementation details:**
- Download using `await file.download_to_drive(destination_path)`
- Use session's cwd for file placement (from session_manager)
- Filename: `telegram_photo_{timestamp}.jpg`
- Clean up old temp photos periodically (or on session close)
- Support photo captions: if photo has caption, send caption as text first, then file path

**Error handling:**
- File download failure -> notify user
- No active session -> inform user to bind a session first
- Disk space issues -> graceful error message

**Future consideration**: This same handler can be extended for documents, but for now only photos are supported. Other media types get a "not supported" reply.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Photos downloaded from Telegram to session cwd
- [ ] #2 File path sent to Claude Code pane
- [ ] #3 Photo caption forwarded as text before file path
- [ ] #4 Confirmation reply sent to user
- [ ] #5 Error handling for download failures and missing sessions
- [ ] #6 Unsupported media types get informative rejection
<!-- AC:END -->
