"""Explicit per-agent skill installation; preserve files not owned by LINCE."""
import argparse
import hashlib
import json
import os
from pathlib import Path

AGENTS = ("claude", "codex", "bob", "pi", "opencode", "gemini", "amp", "goose")


def settings_path():
    return Path.home() / ".config/lince-dashboard/communication.json"


def settings():
    path = settings_path()
    return json.loads(path.read_text()) if path.exists() else {}


def enabled(agent=None):
    try:
        entries = settings()
        return any(v.get("enabled") for v in entries.values()) if agent is None else bool(entries.get(agent, {}).get("enabled"))
    except (OSError, ValueError, AttributeError):
        return False


def skill_path(agent):
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    roots = {
        "claude": Path.home() / ".claude",
        "codex": Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))),
        "bob": Path.home() / ".bob",
        "pi": Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent"))),
        "opencode": config / "opencode",
        "gemini": Path.home() / ".gemini",
        "amp": config / "amp",
        "goose": config / "goose",
    }
    return roots[agent] / "skills/lince-converse/SKILL.md"


def checksum(body):
    return hashlib.sha256(body).hexdigest()


def configure(agent, enable, source):
    data = settings()
    entry = data.get(agent, {})
    path = Path(entry.get("path", str(skill_path(agent))))
    if enable:
        body = (source / "skills/lince-converse/SKILL.md").read_bytes()
        if path.exists() and checksum(path.read_bytes()) not in {entry.get("hash"), checksum(body)}:
            raise ValueError(f"Preserving unowned or edited skill: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        data[agent] = {"enabled": True, "path": str(path), "hash": checksum(body)}
        print(f"Enabled {agent}: installed skill {path}; permits peer text + Enter in its LINCE pane.")
    else:
        if path.exists() and entry.get("hash") == checksum(path.read_bytes()):
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        elif path.exists() and entry:
            print(f"Preserved locally edited skill: {path}")
        data[agent] = {**entry, "enabled": False}
        print(f"Disabled communication for {agent}.")
    config = settings_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(config)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--enable", nargs="+", choices=AGENTS)
    mode.add_argument("--disable", nargs="+", choices=AGENTS)
    mode.add_argument("--refresh", action="store_true")
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--disable-all", action="store_true")
    args = cli.parse_args()
    source = Path(__file__).parent
    if args.list:
        print(" ".join(AGENTS))
    elif args.disable_all:
        for agent in settings():
            configure(agent, False, source)
    elif args.refresh:
        for agent in AGENTS:
            if enabled(agent):
                configure(agent, True, source)
    else:
        for agent in args.enable or args.disable or []:
            configure(agent, bool(args.enable), source)


if __name__ == "__main__":
    main()
