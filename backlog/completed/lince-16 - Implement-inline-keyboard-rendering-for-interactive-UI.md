---
id: LINCE-16
title: Implement inline keyboard rendering for interactive UI
status: Done
assignee: []
created_date: '2026-03-03 14:34'
updated_date: '2026-03-16 12:03'
labels:
  - telebridge
  - interactive-ui
  - telegram
milestone: m-3
dependencies:
  - LINCE-15
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Render detected interactive UI states as Telegram inline keyboards and handle button press callbacks.

**Keyboard layout by UI type:**

**Permission prompt:**
```
[Content of the permission request]
[ ✅ Allow ]  [ ❌ Deny ]
```

**Multi-choice question:**
```
[Question text]
[Option 1]  (highlighted if selected)
[Option 2]
[Option 3]
[⬆️] [⬇️] [Enter ✓] [Esc ✕]
```

**Plan mode / Checkpoint:**
```
[Content]
[⬆️] [⬇️] [Enter ✓] [Esc ✕]
```

**Navigation buttons mapping to send_keys:**
- ⬆️ -> `send_keys(["Up"])`
- ⬇️ -> `send_keys(["Down"])`
- ⬅️ -> `send_keys(["Left"])`
- ➡️ -> `send_keys(["Right"])`
- Enter ✓ -> `send_keys(["Enter"])`
- Esc ✕ -> `send_keys(["Escape"])`
- Space -> `send_keys(["Space"])`
- Tab -> `send_keys(["Tab"])`
- 🔄 Refresh -> re-capture pane and update message

**Callback data serialization:**
- Use callback_data prefix for routing: `"iui:up"`, `"iui:down"`, `"iui:enter"`, `"iui:esc"`, `"iui:refresh"`
- Single CallbackQueryHandler in bot.py dispatches by prefix

**Message management:**
- Track interactive message per (user_id, thread_id) to edit in place
- When UI changes, edit existing message rather than sending new one
- If edit fails (message deleted), send new message
- `clear_interactive_msg()` removes tracking and deletes Telegram message when UI closes

**UI type adaptation:**
- Checkpoint restoration: omit left/right arrows (vertical navigation only)
- Permission prompt: only Allow/Deny buttons, no arrows
- Multi-choice: full navigation set

**Build keyboard function:**
```python
def build_interactive_keyboard(ui_state: InteractiveUIState) -> InlineKeyboardMarkup
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Inline keyboards rendered per UI type with appropriate buttons
- [ ] #2 Button presses translated to correct send_keys calls
- [ ] #3 Messages edited in-place on UI state change
- [ ] #4 Fallback to new message if edit fails
- [ ] #5 Cleanup when interactive UI closes
- [ ] #6 Callback data routing via prefix in single handler
- [ ] #7 Refresh button re-captures pane and updates
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
LINCE-16 Implementation Complete ✅

**Components:**
- `ui_keyboard.py`: Keyboard builder for all UI types
- `ui_message_tracker.py`: Async message tracking with TTL
- `handlers/ui_callbacks.py`: Button press callback handler
- Integration in `bot.py`: `_ui_callback()` and handler registration

**Features:**
- Permission prompts: Allow/Deny + refresh
- Multi-choice: Direct selection + navigation
- Plan/Checkpoint/Model: Full navigation (up/down/enter/esc/refresh)
- Message editing: In-place updates via UIMessageTracker
- Validation: Index bounds checking (0-99)

**Code Quality (simplify skill):**
1. Named constants (MAX_BUTTON_TEXT_LENGTH, MAX_MULTI_CHOICE_OPTIONS)
2. DRY with _build_nav_row() helper
3. O(1) lookups using set
4. Conditional slicing
5. Consistent emoji navigation
6. Specific exception catching

**Test Coverage:** 36 UI-related tests passing
<!-- SECTION:FINAL_SUMMARY:END -->
