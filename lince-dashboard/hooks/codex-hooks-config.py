#!/usr/bin/env python3
"""Install/remove only Lince's handlers, preserving other Codex hooks."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


COMMAND = "codex-status-hook.sh"
EVENTS = (
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PermissionRequest", "PreCompact", "PostCompact", "Stop", "Interrupt",
    "SessionEnd",
)


def update(path: Path, *, remove: bool = False) -> None:
    if remove and not path.exists():
        return
    raw = path.read_text() if path.exists() else None
    data = json.loads(raw) if raw is not None else {}
    hooks = data.setdefault("hooks", {})
    # Validate before editing; a malformed user file must remain untouched.
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"{event}: expected a list of matcher groups")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"{event}: invalid matcher group")
            if any(not isinstance(handler, dict) for handler in group["hooks"]):
                raise ValueError(f"{event}: invalid handler")

    for event in EVENTS:
        groups = hooks.get(event, [])
        remaining = []
        for group in groups:
            handlers = [h for h in group["hooks"] if not (
                h.get("type") == "command" and h.get("command") == COMMAND
            )]
            if handlers == group["hooks"]:
                remaining.append(group)
            elif handlers:
                remaining.append({**group, "hooks": handlers})
        if not remove:
            remaining.append({"hooks": [{
                "type": "command", "command": COMMAND, "timeout": 3,
            }]})
        if remaining:
            hooks[event] = remaining
        else:
            hooks.pop(event, None)

    updated = json.dumps(data, indent=2) + "\n"
    if raw is not None and json.loads(raw) == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".lince.bak")
        suffix = 1
        while backup.exists():
            backup = path.with_name(path.name + f".lince.bak.{suffix}")
            suffix += 1
        shutil.copy2(path, backup)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(updated)
        if path.exists():
            shutil.copymode(path, temp)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


if __name__ == "__main__":
    update(Path(sys.argv[1]), remove="--remove" in sys.argv[2:])
