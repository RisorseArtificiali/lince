#!/usr/bin/env python3
"""Deterministic voice adapter for disposable Zellij UI sessions (no audio)."""

import argparse
import fcntl
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--controller")
parser.add_argument("--request")
args = parser.parse_args()
request = json.loads(args.request)
path = Path(__file__).with_suffix(".json")
with path.with_suffix(".lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = (
        json.loads(path.read_text())
        if path.exists()
        else dict(
            installed=True,
            settings=dict(
                configured=False,
                mode="ptt",
                microphone="default",
                language="auto",
                model="small",
                device="cpu",
                auto_send=False,
            ),
            status="stopped",
            level=3,
            error="",
            buffer="",
            devices=[dict(id="1", name="Fixture microphone")],
            events=[],
            count=0,
        )
    )
    action = request["action"]
    state["events"] = [e for e in state["events"] if e["sequence"] > request.get("ack", 0)]
    if action == "save":
        state["settings"] = request["settings"] | {"configured": True}
    elif action in ("stop", "shutdown"):
        state["status"] = "stopped"
    elif action == "start":
        state["status"] = "listening"
    elif action == "mute":
        state["status"] = "listening" if state["status"] == "muted" else "muted"
    elif action == "ptt":
        state["status"] = "listening" if state["status"] == "recording" else "recording"
        if state["status"] == "listening":
            state["count"] += 1
            state["events"].append(dict(sequence=state["count"], text="VOICE_FIXTURE_TEXT"))
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state))
    temporary.replace(path)
    print(json.dumps(state))
