# Telebridge Development Guide

## Project Overview

Telegram-to-Claude Code bridge that enables Telegram-based interaction with Claude Code sessions running in tmux/zellij.

## Quick Commands

Use helper scripts in `scripts/` to avoid PYTHONPATH issues:

```bash
# Run tests
./scripts/test.sh                    # Run all tests
./scripts/test.sh -v --tb=short      # Verbose with short traceback
./scripts/test.sh tests/test_app.py  # Run specific test file

# Run the bot
./scripts/run.sh                       # Run with default config
./scripts/run.sh --config custom.toml  # Run with custom config

# Lint/type check
./scripts/lint.sh

# Format code
./scripts/format.sh
```

## Build / Test

- **Tests**: `./scripts/test.sh` (uses pytest)
- **Type checking**: `./scripts/lint.sh` (uses pyright)
- **Formatting**: `./scripts/format.sh` (uses ruff)

## Code Style

- Python 3.11+
- ruff defaults, line length 119
- Use absolute imports (never relative)
- Type hints where practical
- snake_case for functions/variables, CamelCase for classes

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram      │────>│   TelebridgeApp   │────>│   Claude Code    │
│   (python-telegram-bot) │                  │     │   (JSONL session) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        ▲                        │                        ▲
        │                        │                        │
        ▼                        ▼                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  MessageQueue   │     │  SessionManager  │     │  MultiplexerBridge│
│  (per-user queue)│     │  (topic-pane map)│     │  (tmux/zellij)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | TelebridgeApp class - main entry point |
| `bot.py` | DEPRECATED - use TelebridgeApp instead |
| `session_manager.py` | Topic-pane-session binding |
| `message_queue.py` | Per-user async message queue |
| `session_monitor.py` | JSONL file polling for outbound messages |
| `multiplexer.py` | Protocol for terminal multiplexers |
| `tmux_bridge.py` | tmux implementation |
| `zellij_bridge.py` | Zellij implementation |

## Configuration

Copy `config.example.toml` to `~/.telebridge/config.toml`:

```toml
[telegram]
bot_token = "YOUR_BOT_TOKEN"
allowed_users = [123456789]  # Your Telegram user ID

[session]
auto_bind = true
```
