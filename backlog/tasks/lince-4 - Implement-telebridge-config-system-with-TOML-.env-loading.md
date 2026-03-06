---
id: LINCE-4
title: Implement telebridge config system with TOML + .env loading
status: To Do
assignee: []
created_date: '2026-03-03 14:31'
labels:
  - telebridge
  - config
milestone: m-0
dependencies:
  - LINCE-3
references:
  - voxcode/src/voxcode/config.py
  - ccbot src/ccbot/config.py pattern
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/config.py` following VoxCode's dataclass-based TOML config pattern, extended with .env support for secrets.

**Config dataclasses:**
```python
@dataclass
class TelegramConfig:
    bot_token: str = ""              # from .env TELEGRAM_BOT_TOKEN
    allowed_users: list[int] = field(default_factory=list)  # from .env ALLOWED_USERS

@dataclass
class SessionConfig:
    poll_interval: float = 2.0       # seconds between JSONL polls
    auto_bind: bool = True           # auto-bind topics to sessions
    state_dir: str = ""              # default: ~/.telebridge/

@dataclass
class VoiceConfig:
    enabled: bool = True
    language: str = "auto"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"

@dataclass
class MultiplexerConfig:
    backend: str = "auto"            # auto, tmux, zellij
    send_enter: bool = True

@dataclass
class ZellijConfig:
    target_pane: str = "up"
    auto_detect: bool = True

@dataclass
class TmuxConfig:
    target_pane: str = ""
    auto_detect: bool = True

@dataclass
class TelebridgeConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    multiplexer: MultiplexerConfig = field(default_factory=MultiplexerConfig)
    zellij: ZellijConfig = field(default_factory=ZellijConfig)
    tmux: TmuxConfig = field(default_factory=TmuxConfig)
```

**Loading behavior:**
1. `load_config(path=None)` searches: explicit path -> ./config.toml -> ~/.config/telebridge/config.toml -> defaults
2. Uses `tomllib` (Python 3.11+ built-in) for TOML parsing
3. After TOML load, overlay .env values: `python-dotenv` loads from ./. env and ~/.telebridge/.env
4. `TELEGRAM_BOT_TOKEN` and `ALLOWED_USERS` from env vars override TOML values
5. Security scrubbing: after capture, pop `TELEGRAM_BOT_TOKEN` and `ALLOWED_USERS` from `os.environ` so child processes (Claude Code) never see them

**Claude projects path resolution (from ccbot pattern):**
Priority: `CCBOT_CLAUDE_PROJECTS_PATH` env -> `CLAUDE_CONFIG_DIR/projects` -> `~/.claude/projects`

**State directory:** `~/.telebridge/` for state.json, session_map.json, monitor_state.json

**Pattern reference:** Replicate voxcode/src/voxcode/config.py's `load_config()` with `setattr()` dynamic assignment from TOML sections.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 load_config() loads TOML with all sections
- [ ] #2 .env values override TOML for secrets
- [ ] #3 Security scrubbing removes tokens from os.environ after capture
- [ ] #4 Default config is valid without any config file
- [ ] #5 Claude projects path resolution follows priority chain
<!-- AC:END -->
