#!/usr/bin/env python3
"""Install/update/remove the Gemini, Amp and Goose dashboard integrations."""
import argparse
import hashlib
import json
import os
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
GEMINI_EVENTS = ("SessionStart", "SessionEnd", "BeforeAgent", "AfterAgent", "BeforeModel",
                 "BeforeTool", "AfterTool", "Notification")
GOOSE_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "PreToolUse",
                "PostToolUse", "PostToolUseFailure")
COMMAND = 'python3 "$HOME/.gemini/lince-status.py" gemini'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def configure(remove=False):
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    manifest = config / "lince-dashboard/native-hooks.json"
    owned = json.loads(manifest.read_text()) if manifest.exists() else {}
    goose = home / ".agents/plugins/lince-status"
    hook_data = {"hooks": {event: [{"hooks": [{"type": "command",
                  "command": 'python3 "${PLUGIN_ROOT}/scripts/status.py" goose', "timeout": 3}]}]
                  for event in GOOSE_EVENTS}}
    files = {
        home / ".gemini/lince-status.py": (SOURCE / "native-status-hook.py").read_bytes(),
        config / "amp/plugins/lince-status.js": (SOURCE / "amp-status-hook.js").read_bytes(),
        goose / "plugin.json": json.dumps({"name": "lince-status", "version": "1.0.0",
                                          "description": "Lince dashboard lifecycle status"}, indent=2).encode(),
        goose / "hooks/hooks.json": json.dumps(hook_data, indent=2).encode(),
        goose / "scripts/status.py": (SOURCE / "native-status-hook.py").read_bytes(),
    }
    # Check the complete installation before writing anything. Preserve edited files.
    if not remove:
        for path, content in files.items():
            if path.exists() and path.read_bytes() != content and digest(path.read_bytes()) != owned.get(str(path)):
                raise SystemExit(f"Preserving unowned or modified integration: {path}")
    settings = home / ".gemini/settings.json"
    data = json.loads(settings.read_text()) if settings.exists() else {}
    hooks = data.setdefault("hooks", {})
    for event in GEMINI_EVENTS:
        groups = []
        for group in hooks.get(event, []):
            handlers = [h for h in group.get("hooks", []) if h.get("command") != COMMAND]
            if handlers or "hooks" not in group:
                groups.append(dict(group, hooks=handlers) if "hooks" in group else group)
        if not remove:
            groups.append({"hooks": [{"type": "command", "name": "lince-status", "command": COMMAND, "timeout": 3000}]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        data.pop("hooks", None)
    if not remove or settings.exists():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n")
    if remove:
        for name, checksum in list(owned.items()):
            path = Path(name)
            if path in files and path.is_file() and digest(path.read_bytes()) == checksum:
                path.unlink()
                del owned[name]
            elif path.exists():
                print(f"Preserving modified integration: {path}")
    else:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            owned[str(path)] = digest(content)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(owned, indent=2) + "\n")
    print("Gemini, Amp and Goose dashboard integrations " + ("removed." if remove else "installed. Restart agent panes."))
    if not remove:
        print("Requires Gemini lifecycle hooks, Amp thread.state plugin API and Goose Open Plugins hooks.")
        print("Older agent versions or disabled integrations cannot report idle; messages will remain pending.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    configure(parser.parse_args().remove)
