---
id: LINCE-22
title: Implement directory browser for session working directory selection
status: To Do
assignee: []
created_date: '2026-03-03 14:36'
labels:
  - telebridge
  - ui
milestone: m-6
dependencies:
  - LINCE-13
references:
  - ccbot src/ccbot/handlers/directory_browser.py pattern
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create a filesystem navigation UI in Telegram for selecting the working directory when starting a new Claude Code session.

**Flow:**
1. User triggers new session creation (from session picker or `/new` command)
2. Bot displays current directory contents as inline keyboard buttons
3. Each directory is a button; selecting navigates into it
4. Navigation buttons: [📁 ..] (parent), [✅ Select] (confirm cwd), [❌ Cancel]
5. On confirm: start Claude Code in selected directory

**Inline keyboard layout:**
```
📂 Current: /home/user/projects
─────────────────────────────
[📁 project-a/]
[📁 project-b/]
[📁 project-c/]
─────────────────────────────
[⬅ Page 1/3 ➡]
[📁 ..] [✅ Select] [❌ Cancel]
```

**Implementation details:**
- Start from home directory or last used directory
- List only directories (not files) — configurable to show hidden dirs
- Pagination: max 8 directories per page
- Callback data: `"dir:select:{path}"`, `"dir:up"`, `"dir:page:{n}"`, `"dir:confirm"`, `"dir:cancel"`
- Edit message in-place on navigation (don't send new messages)
- Security: validate paths are within allowed scope (don't navigate above home or into system dirs)

**State tracking:**
- Track browsing state per (user_id, thread_id) in context.user_data
- Clean up state on confirm, cancel, or timeout

**Config option:** `show_hidden_dirs` (default false) — whether to list dotfiles/dotdirs.

**Integration**: Once directory selected, pass to session creation flow (LINCE-13) as cwd parameter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Directory listing displayed as inline keyboard buttons
- [ ] #2 Navigation into subdirectories works
- [ ] #3 Parent directory (..) navigation works
- [ ] #4 Pagination for directories with many entries
- [ ] #5 Select confirms cwd and triggers session creation
- [ ] #6 Cancel aborts and cleans up state
- [ ] #7 Hidden dirs controlled by config option
- [ ] #8 Path validation prevents navigation outside safe scope
<!-- AC:END -->
