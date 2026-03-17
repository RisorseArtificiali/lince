---
id: LINCE-40
title: Support multiple photos per Telegram message
status: Done
assignee: []
created_date: '2026-03-16 13:23'
updated_date: '2026-03-17 10:11'
labels:
  - enhancement
  - telegram
  - media
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Telegram messages can contain multiple photos (an album). Currently LINCE-18 only handles single photos via `message.photo[-1]` (last/highest resolution).

**Requirements:**
- Detect when `message.photo` contains multiple sizes (album)
- Download all unique photos in the album
- Generate sequential filenames (e.g., `telegram_photo_123_1.jpg`, `telegram_photo_123_2.jpg`)
- Send all file paths to Claude Code
- Consider creating a zip file for batch analysis

**Technical notes:**
- Telegram `message.photo` is an array of sizes
- Albums come as multiple messages with `media_group_id`
- Need to handle grouping by `media_group_id`

**References:**
- LINCE-18 photo handler at `telebridge/src/telebridge/handlers/media.py`
<!-- SECTION:DESCRIPTION:END -->
