---
id: LINCE-3
title: Scaffold telebridge module structure
status: To Do
assignee: []
created_date: '2026-03-03 14:30'
labels:
  - telebridge
  - scaffolding
milestone: m-0
dependencies: []
references:
  - voxcode/pyproject.toml
  - voxcode/src/voxcode/__init__.py
  - voxcode/src/voxcode/__main__.py
  - claudedocs/telebridge-proposal.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create the `telebridge/` directory as a new LINCE module following VoxCode's packaging patterns.

**Directory structure:**
```
telebridge/
├── src/telebridge/
│   ├── __init__.py           # __version__ = "0.1.0"
│   ├── __main__.py           # python -m telebridge
│   ├── cli.py                # argparse entry point
│   ├── config.py             # TOML + .env config loading
│   ├── bot.py                # Telegram Application setup
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── messages.py       # Text message routing
│   │   ├── commands.py       # Bot commands
│   │   ├── callbacks.py      # Inline keyboard callbacks
│   │   ├── voice.py          # Voice messages
│   │   └── media.py          # Photos and media
│   ├── session_monitor.py    # JSONL polling
│   ├── transcript_parser.py  # Claude Code output parser
│   ├── response_formatter.py # Markdown -> MarkdownV2
│   ├── interactive_ui.py     # Terminal UI -> inline keyboard
│   ├── screenshot.py         # Terminal -> PNG
│   ├── hook.py               # SessionStart hook installer
│   └── session_manager.py    # Topic-pane-session mapping
├── pyproject.toml
├── config.example.toml
└── README.md
```

**pyproject.toml requirements:**
- name: "telebridge"
- requires-python: ">=3.11"
- build-system: hatchling (same as voxcode)
- entry point: `telebridge = "telebridge.cli:main"`
- dependencies: python-telegram-bot[rate-limiter]>=21.0, aiofiles>=24.0.0, python-dotenv>=1.0.0, Pillow>=10.0.0, telegramify-markdown>=0.5.0, numpy>=1.24.0
- optional dependency group [voice]: faster-whisper>=1.1.0
- dev dependencies: ruff, pyright, pytest, pytest-asyncio

**config.example.toml**: Create with all sections documented (telegram, session, voice, multiplexer, zellij, tmux). Secrets (bot_token) should reference .env file pattern, not be in TOML.

**Pattern reference**: Follow voxcode/pyproject.toml and voxcode/src/voxcode/ structure exactly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Directory structure matches the spec above
- [ ] #2 pyproject.toml valid and installable with `uv pip install -e .`
- [ ] #3 config.example.toml documents all config sections
- [ ] #4 `python -m telebridge --help` runs without error
- [ ] #5 ruff check passes on all files
<!-- AC:END -->
