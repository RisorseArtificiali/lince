"""Configuration loading with TOML + .env support."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import tomllib
from dotenv import load_dotenv


@dataclass
class TelegramConfig:
    bot_token: str = ""
    allowed_users: list[int] = field(default_factory=list)


@dataclass
class SessionConfig:
    poll_interval: float = 2.0
    auto_bind: bool = True
    state_dir: str = ""


@dataclass
class VoiceConfig:
    enabled: bool = True
    language: str = "auto"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"


@dataclass
class MultiplexerConfig:
    backend: str = "auto"
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


def _apply_section(config_obj, data: dict) -> None:
    """Apply dictionary values to a config dataclass instance."""
    for key, value in data.items():
        if hasattr(config_obj, key):
            setattr(config_obj, key, value)


def get_claude_projects_path() -> Path:
    """Resolve Claude projects directory path.

    Priority: CCBOT_CLAUDE_PROJECTS_PATH -> CLAUDE_CONFIG_DIR/projects -> ~/.claude/projects
    """
    if env_path := os.environ.get("CCBOT_CLAUDE_PROJECTS_PATH"):
        return Path(env_path)
    if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(config_dir) / "projects"
    return Path.home() / ".claude" / "projects"


def get_state_dir(config: TelebridgeConfig) -> Path:
    """Resolve state directory path for session persistence."""
    return Path(config.session.state_dir) if config.session.state_dir else Path.home() / ".telebridge"


def load_config(path: str | None = None) -> TelebridgeConfig:
    """Load configuration from TOML file and .env overrides.

    Search order for TOML: explicit path -> ./config.toml -> ~/.config/telebridge/config.toml
    .env files: ./.env and ~/.telebridge/.env

    Security: TELEGRAM_BOT_TOKEN and ALLOWED_USERS are scrubbed from os.environ after loading.
    """
    config = TelebridgeConfig()

    # Load .env files first (lower priority than TOML)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path.home() / ".telebridge" / ".env")

    # Resolve config path
    if path is None:
        candidates = [
            Path.cwd() / "config.toml",
            Path.home() / ".config" / "telebridge" / "config.toml",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                break

    # Load TOML configuration
    if path and Path(path).exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)

        section_map = {
            "telegram": config.telegram,
            "session": config.session,
            "voice": config.voice,
            "multiplexer": config.multiplexer,
            "zellij": config.zellij,
            "tmux": config.tmux,
        }
        for section_name, config_obj in section_map.items():
            if section_name in data:
                _apply_section(config_obj, data[section_name])

    # Apply .env overrides (highest priority)
    if bot_token := os.environ.get("TELEGRAM_BOT_TOKEN"):
        config.telegram.bot_token = bot_token

    if allowed_users := os.environ.get("ALLOWED_USERS"):
        try:
            config.telegram.allowed_users = [
                int(u.strip()) for u in allowed_users.split(",") if u.strip()
            ]
        except ValueError:
            pass  # Ignore malformed ALLOWED_USERS

    # Security: scrub sensitive values from environment
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ.pop("ALLOWED_USERS", None)

    return config
