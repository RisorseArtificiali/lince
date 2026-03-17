---
id: LINCE-46
title: >-
  Add test coverage for media handlers (photo_handler,
  unsupported_media_handler)
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 09:11'
labels:
  - testing
  - quality
  - coverage
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
LINCE-18 added `photo_handler` and `unsupported_media_handler` but no corresponding tests were added.

**Missing Test Coverage:**
- `telebridge/tests/test_interactive_ui.py` exists
- `telebridge/tests/test_message_queue.py` exists
- `telebridge/tests/test_session_lifecycle.py` exists
- `telebridge/tests/test_ui_keyboard.py` exists

**Test Cases Needed for media.py:**
1. `photo_handler` with valid photo and active session
2. `photo_handler` with unauthorized user (whitelist check)
3. `photo_handler` with no active session (bind prompt)
4. `photo_handler` with photo containing caption
5. `photo_handler` with download errors
6. `photo_handler` sends file path to correct pane
7. `unsupported_media_handler` rejects documents
8. `unsupported_media_handler` rejects videos
9. `unsupported_media_handler` provides helpful error message

**Test Strategy:**
- Mock `get_bridge()`, `get_session_manager()`, `Update` objects
- Use `pytest-asyncio` for async handler tests
- Verify `send_keys` called with correct pane_key and file path
- Verify Telegram reply messages sent

**Reference:**
- telebridge/src/telebridge/handlers/media.py
- telebridge/tests/ (existing test patterns)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 photo_handler tests: unauthorized user, no photo, no session, valid photo, caption forwarding, download errors
- [ ] #2 document_handler tests: unauthorized user, file size limit, valid document, file path forwarding
- [ ] #3 unsupported_media_handler tests: unauthorized user, video rejection, audio rejection, helpful error message
- [ ] #4 All 191 tests pass
- [ ] #5 Tests follow existing project patterns (AsyncMock, MagicMock, pytest.mark.asyncio)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Summary

Added comprehensive test coverage for media handlers in `tests/test_media_handlers.py`.

### Test Coverage Added (15 tests)

**TestPhotoHandler (6 tests):**
- `test_unauthorized_user_returns_early` - Auth check
- `test_no_photo_returns_early` - Empty photo handling
- `test_no_session_shows_bind_prompt` - Session resolution failure
- `test_valid_photo_downloads_and_confirms` - Happy path
- `test_photo_with_caption_forwards_caption` - Caption forwarding
- `test_download_error_shows_error_message` - Error handling

**TestDocumentHandler (4 tests):**
- `test_unauthorized_user_returns_early` - Auth check
- `test_file_too_large_rejected` - 50MB limit enforcement
- `test_valid_document_downloads_and_confirms` - Happy path
- `test_document_forwards_file_path` - File path sent to bridge

**TestUnsupportedMediaHandler (5 tests):**
- `test_unauthorized_user_returns_early` - Auth check
- `test_video_shows_unsupported_message` - Video rejection
- `test_audio_shows_unsupported_message` - Audio rejection
- `test_message_lists_supported_types` - Helpful error message
- `test_no_message_returns_early` - Edge case handling

### Test Patterns Used
- `pytest.mark.asyncio` for async handlers
- `AsyncMock` for async methods (reply_text, get_file, download_to_drive)
- `MagicMock` for sync objects (Update, message, document)
- `patch` for dependency injection (get_app)

All 191 tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
