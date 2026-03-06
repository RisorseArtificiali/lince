---
id: LINCE-16
title: Implement inline keyboard rendering for interactive UI
status: To Do
assignee: []
created_date: '2026-03-03 14:34'
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
