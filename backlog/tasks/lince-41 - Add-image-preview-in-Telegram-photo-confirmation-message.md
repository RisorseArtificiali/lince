---
id: LINCE-41
title: Add image preview in Telegram photo confirmation message
status: To Do
assignee: []
created_date: '2026-03-16 13:23'
labels:
  - enhancement
  - ux
  - telegram
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Currently photo confirmation only shows filename and location. Add a thumbnail preview so users can verify the correct image was received.

**Requirements:**
- Include thumbnail in confirmation reply
- Use `message.reply_photo()` with downloaded file
- Add caption with metadata (filename, size, location)
- Handle large files gracefully (may need to resize thumbnail)

**References:**
- LINCE-18 photo handler confirmation at line 79-84 in `media.py`
- Telegram Bot API `reply_photo()` method
<!-- SECTION:DESCRIPTION:END -->
