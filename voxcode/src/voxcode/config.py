"""Configuration loading and defaults."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeneralConfig:
    mode: str = "ptt"
    language: str = "auto"
    auto_send: bool = False


@dataclass
class WhisperConfig:
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"


@dataclass
class VADConfig:
    threshold: float = 0.015
    silence_duration: float = 1.5
    pre_roll: float = 0.3


@dataclass
class PTTConfig:
    key: str = "space"
    clipboard_key: str = "tab"


@dataclass
class CommandsConfig:
    enabled: bool = True
    prefix: str = "comando"


@dataclass
class AudioConfig:
    device: int | None = None  # sounddevice device index, None = system default


@dataclass
class MultiplexerConfig:
    backend: str = "auto"  # "auto" | "tmux" | "zellij"
    send_enter: bool = False
    launch_command: str = "claude"


@dataclass
class TmuxConfig:
    auto_detect: bool = True
    target_pane: str = ""
    launch_command: str = "claude"  # backward-compat, prefer [multiplexer] launch_command


@dataclass
class ZellijConfig:
    auto_detect: bool = True
    target_pane: str = ""  # "" | "next" | "previous" | "left" | "right" | "up" | "down"


@dataclass
class VoxCodeConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    ptt: PTTConfig = field(default_factory=PTTConfig)
    commands: CommandsConfig = field(default_factory=CommandsConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    multiplexer: MultiplexerConfig = field(default_factory=MultiplexerConfig)
    tmux: TmuxConfig = field(default_factory=TmuxConfig)
    zellij: ZellijConfig = field(default_factory=ZellijConfig)


def _apply_section(config_obj, data: dict):
    for key, value in data.items():
        if hasattr(config_obj, key):
            setattr(config_obj, key, value)


def load_config(path: str | None = None) -> VoxCodeConfig:
    config = VoxCodeConfig()

    if path is None:
        candidates = [
            Path.cwd() / "config.toml",
            Path.home() / ".config" / "voxcode" / "config.toml",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                break

    if path and Path(path).exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)

        section_map = {
            "general": config.general,
            "whisper": config.whisper,
            "vad": config.vad,
            "ptt": config.ptt,
            "commands": config.commands,
            "audio": config.audio,
            "multiplexer": config.multiplexer,
            "tmux": config.tmux,
            "zellij": config.zellij,
        }
        for section_name, config_obj in section_map.items():
            if section_name in data:
                _apply_section(config_obj, data[section_name])

    return config
