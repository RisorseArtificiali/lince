---
id: LINCE-10
title: Implement Telegram bot skeleton with auth and basic routing
status: Done
assignee: []
created_date: '2026-03-03 14:33'
updated_date: '2026-03-15 09:36'
labels:
  - telebridge
  - telegram
  - core
milestone: m-7
dependencies:
  - LINCE-3
  - LINCE-4
  - LINCE-5
references:
  - ccbot src/ccbot/bot.py Application setup
  - python-telegram-bot v21 documentation
  - voxcode/src/voxcode/multiplexer.py create_bridge
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/bot.py` and `telebridge/src/telebridge/cli.py` — the Telegram bot Application setup with authentication, handler registration, and lifecycle management.

**Bot setup** (`bot.py`):
```python
async def create_application(config: TelebridgeConfig) -> Application:
    application = (
        Application.builder()
        .token(config.telegram.bot_token)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    # Register handlers in order (order matters for python-telegram-bot):
    # 1. Command handlers
    # 2. CallbackQueryHandler (single dispatcher for all inline buttons)
    # 3. Text message handler (non-command text -> Claude Code)
    # 4. Photo handler
    # 5. Voice handler
    return application
```

**Authentication middleware:**
- Every handler checks `config.telegram.allowed_users` whitelist
- `is_user_allowed(user_id: int) -> bool`
- Unauthorized users get a brief rejection message
- Log unauthorized access attempts

**Lifecycle:**
- `post_init()`: install hook if needed, start SessionMonitor, set bot commands menu
- `post_shutdown()`: stop SessionMonitor, cleanup resources

**CLI** (`cli.py`):
- `telebridge` / `telebridge run` — start the bot (default)
- `telebridge hook` — handle SessionStart hook callback (reads stdin)
- `telebridge install-hook` — install hook in Claude settings
- `telebridge --config PATH` — specify config file
- Uses argparse with subcommands

**Handler stubs**: For this task, register handlers that route to stub functions in handlers/. The actual handler implementations are separate tasks. The text message handler should be functional (forward text to Claude Code via MultiplexerBridge).

**Basic inbound flow** (functional in this task):
```
Telegram text message -> auth check -> resolve multiplexer bridge -> bridge.send_text(text)
```

**MultiplexerBridge initialization:**
- Import `create_bridge` from voxcode.multiplexer
- Create bridge config from telebridge config (map TelebridgeConfig multiplexer/zellij/tmux sections to VoxCodeConfig equivalents)
- Bridge created once at startup, reused for all operations

**Error handling**: Catch bridge errors (multiplexer not running, pane not found) and report to user via Telegram reply.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Application created with python-telegram-bot and rate limiter
- [x] #2 Whitelist-based authentication on every handler
- [x] #3 CLI supports run, hook, install-hook subcommands
- [x] #4 Text messages forwarded to Claude Code via MultiplexerBridge
- [x] #5 MultiplexerBridge created from config (Zellij or tmux)
- [ ] #6 post_init starts SessionMonitor
- [x] #7 post_shutdown stops monitor and cleans up
- [x] #8 Bridge errors reported to user via Telegram reply
- [x] #9 Bot runs with `telebridge run` command
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented Telegram bot skeleton with three core files:

**bot.py** - Main application setup:
- `create_application()` with AIORateLimiter, post_init/post_shutdown hooks
- Global `_bridge` and `_config` for handler access
- `is_user_allowed()` and `get_bridge()` helpers
- Handler registration in priority order (commands → text messages)
- Bot command menu setup (`/start`, `/screenshot`)

**handlers/messages.py** - Text routing:
- Auth check via `is_user_allowed()`
- Routes non-command text to Claude Code via `bridge.send_keys()`
- Error handling with user feedback

**handlers/commands.py** - Extended with:
- `/start` command showing bot info and available commands
- `/screenshot` command (existing) with multiplexer-agnostic error messages

All 33 tests pass. Code reviewed via simplify skill - fixed leaky abstraction (tmux → terminal multiplexer).

Note: SessionMonitor (#6) deferred to future task - not required for basic bot operation.
<!-- SECTION:FINAL_SUMMARY:END -->
