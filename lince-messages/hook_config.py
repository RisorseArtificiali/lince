"""Remove retired LINCE mailbox hooks without changing unrelated user hooks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

# Legacy hook names retained only for removal during migration/uninstall.
EVENTS = {
    "claude": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification", "Stop", "SessionEnd"),
    "codex": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "PreCompact", "PostCompact", "Stop", "Interrupt", "SessionEnd"),
    "bob": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "PostCompact", "Stop"),
}


def update(path: Path, agent: str, remove=True):
    command = f"lince-msg-hook {agent}"
    if remove and not path.exists():
        return
    raw = path.read_text() if path.exists() else None
    data = json.loads(raw) if raw else {}
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError("Expected an object with an optional hooks object")
    hooks = data.setdefault("hooks", {})
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"{event}: expected matcher groups")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"{event}: invalid matcher group")
            if any(not isinstance(handler, dict) for handler in group["hooks"]):
                raise ValueError(f"{event}: invalid handler")
    for event in EVENTS[agent]:
        remaining = []
        for group in hooks.get(event, []):
            handlers = [handler for handler in group["hooks"] if not (
                handler.get("type") == "command" and handler.get("command") == command)]
            if handlers == group["hooks"]:
                remaining.append(group)
            elif handlers:
                remaining.append({**group, "hooks": handlers})
        if remaining:
            hooks[event] = remaining
        else:
            hooks.pop(event, None)
    if raw is not None and json.loads(raw) == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".lince-messages.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output, indent=2)
            output.write("\n")
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=EVENTS)
    parser.add_argument("settings", type=Path)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    update(args.settings, args.agent, True)
