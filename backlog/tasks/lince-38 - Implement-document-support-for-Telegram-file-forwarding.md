---
id: LINCE-38
title: Implement document support for Telegram file forwarding
status: Done
assignee: []
created_date: '2026-03-16 13:23'
updated_date: '2026-03-16 17:20'
labels:
  - enhancement
  - telegram
  - media
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Currently telebridge only supports photo messages. Users should be able to send documents (PDFs, code files, etc.) from Telegram to Claude Code for analysis.

**Requirements:**
- Add `document_handler` in `media.py`
- Download documents to session's `cwd`
- Support common file types (PDF, text, code files)
- Forward file path to Claude Code like photos
- Add file size validation (Telegram limit ~50MB for premium)
- Unsupported file types should give helpful error

**Handler priority:** Register after photo handler, before unsupported media handler

**References:**
- LINCE-18 implemented photo forwarding pattern
- `telebridge/src/telebridge/handlers/media.py`
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Implementation Summary

**Added document support for Telegram file forwarding:**

### Changes Made
1. **`media.py`** - Added `document_handler()` function:
   - Downloads documents to session's cwd with timestamp prefix
   - Preserves original filename
   - Validates file size (50MB max)
   - Forwards file path to Claude Code via bridge
   - Sends confirmation with filename, size, and location

2. **`bot.py`** - Updated handler registration:
   - Added `document_handler` import
   - Registered document handler after photo, before unsupported media
   - Removed `filters.Document.ALL` from `UNSUPPORTED_MEDIA_FILTER`
   - Updated unsupported media message to list supported types

### File Size Constants
- `MAX_FILE_SIZE = 50MB` (Telegram Premium limit)

### Testing Notes
- Manual testing recommended with PDF, code files, and text files
- Test oversized file rejection (>50MB)

### Related Tasks (Refactoring Opportunities)
- LINCE-42: Extract duplicated bridge-session initialization checks
- LINCE-43: Extract duplicated session-resolution error handling
- LINCE-39/48: Automatic cleanup of downloaded media
<!-- SECTION:FINAL_SUMMARY:END -->
