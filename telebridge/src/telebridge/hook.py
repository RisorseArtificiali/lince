"""Claude Code SessionStart hook installer and handler."""

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from telebridge.config import get_state_dir, load_config


def get_claude_settings_path() -> Path:
    """Get path to Claude Code settings file."""
    return Path.home() / ".claude" / "settings.json"


def get_session_map_path() -> Path:
    """Get path to session map file."""
    config = load_config()
    state_dir = get_state_dir(config)
    return state_dir / "session_map.json"


def get_lock_path() -> Path:
    """Get path to lock file for session map writes."""
    config = load_config()
    state_dir = get_state_dir(config)
    return state_dir / "session_map.lock"


def detect_tmux_context() -> str | None:
    """Detect tmux session context.

    Returns session key like "session_name:window_id" or None if not in tmux.
    """
    if not os.environ.get("TMUX"):
        return None

    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}:#{window_id}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def detect_zellij_context() -> str | None:
    """Detect Zellij session context.

    Returns session key like "session_name:tab_index" or None if not in Zellij.
    """
    session_name = os.environ.get("ZELLIJ_SESSION_NAME")
    if not session_name:
        return None

    # Zellij doesn't expose tab index directly in env
    # Use session name with a placeholder tab index
    return f"{session_name}:0"


def detect_multiplexer_context() -> str | None:
    """Detect current multiplexer context (tmux or Zellij).

    Returns session key or None if not in a multiplexer.
    """
    # Try tmux first
    if context := detect_tmux_context():
        return context
    # Try Zellij
    return detect_zellij_context()


def validate_session_id(session_id: str) -> bool:
    """Validate that session_id is a valid UUID format."""
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False


def validate_cwd(cwd: str) -> bool:
    """Validate that cwd is an absolute path."""
    return os.path.isabs(cwd)


def install_hook() -> bool:
    """Install SessionStart hook in Claude Code settings.

    Returns True if hook was installed, False if already present.
    """
    settings_path = get_claude_settings_path()
    settings_dir = settings_path.parent

    # Ensure directory exists
    settings_dir.mkdir(parents=True, exist_ok=True)

    # Read existing settings or create empty
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    # Ensure hooks structure exists
    # Format: {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "...", "timeout": 5}]}]}}
    if "hooks" not in settings:
        settings["hooks"] = {}

    if "SessionStart" not in settings["hooks"]:
        settings["hooks"]["SessionStart"] = []

    session_start_hooks = settings["hooks"]["SessionStart"]

    # Check if already installed (search in nested hooks arrays)
    hook_command = "cd /home/pantinor/data/repo/personal/lince/telebridge && uv run telebridge hook"
    for hook_group in session_start_hooks:
        if isinstance(hook_group, dict) and "hooks" in hook_group:
            for hook in hook_group["hooks"]:
                if isinstance(hook, dict) and hook.get("command") == hook_command:
                    return False  # Already installed

    # Add new hook in the expected nested format
    new_hook_group = {
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
                "timeout": 5,
            }
        ]
    }
    session_start_hooks.append(new_hook_group)

    # Write back atomically
    fd, temp_path = tempfile.mkstemp(dir=settings_dir, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(settings, f, indent=2)
        os.replace(temp_path, settings_path)
    except Exception:
        os.unlink(temp_path)
        raise

    return True


def handle_hook() -> None:
    """Handle SessionStart hook callback from Claude Code.

    Reads JSON from stdin, detects multiplexer context, writes session_map.json.
    """
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")

    # Validate inputs
    if not validate_session_id(session_id):
        print(f"Error: Invalid session_id format: {session_id}", file=sys.stderr)
        sys.exit(1)

    if not validate_cwd(cwd):
        print(f"Error: cwd must be an absolute path: {cwd}", file=sys.stderr)
        sys.exit(1)

    # Detect multiplexer context
    session_key = detect_multiplexer_context()
    if not session_key:
        # Not in a multiplexer, nothing to map
        return

    # Ensure state directory exists
    config = load_config()
    state_dir = get_state_dir(config)
    state_dir.mkdir(parents=True, exist_ok=True)

    session_map_path = get_session_map_path()
    lock_path = get_lock_path()

    # Read existing session map
    session_map: dict = {}
    if session_map_path.exists():
        with open(session_map_path) as f:
            session_map = json.load(f)

    # Update entry
    session_map[session_key] = {
        "session_id": session_id,
        "cwd": cwd,
    }

    # Write atomically with locking
    fd, temp_path = tempfile.mkstemp(dir=state_dir, suffix=".json")
    try:
        # Acquire exclusive lock
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(session_map, f, indent=2)
                os.replace(temp_path, session_map_path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
