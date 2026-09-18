#!/usr/bin/env python3
"""Opt-in real Bob TUI / Claude headless cross-agent messaging probe.

Requires authenticated Bob Shell SSO, Claude access, and the pinned pyte test
venv from lince-dashboard/tests/setup-ui-test-env.sh. Uses real model calls.
Bob retains its original TUI. Only this disposable probe enables --auto-approve
for the explicitly requested messaging commands; production launch flags and
user configuration are untouched. Permission/human-intervention evidence is
recorded separately. Private temporary artifacts are printed at startup.
"""

import fcntl
import json
import os
import pathlib
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import uuid
import pyte

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from service import Server
from store import Store
from adapters import capabilities, EVENTS

root = pathlib.Path(__file__).resolve().parents[1]

for agent, version in [("bob", "2.0.4"), ("claude", "2.1.272")]:
    output = subprocess.check_output([agent, "--version"], text=True, timeout=10)
    assert re.search(r"\b" + re.escape(version) + r"\b", output), (
        "Review adapter version before probe: " + output
    )
base = pathlib.Path(tempfile.mkdtemp(prefix="lince-bob-pair-tui-"))
print("evidence:", base, flush=True)
store = Store(base / "db", "admin")


def host(op, **args):
    return store.handle({"v": 1, "token": "admin", "op": "host." + op, "args": args})


def rpc(actor, op, **args):
    return store.handle({"v": 1, "token": actor["token"], "op": op, "args": args})


actors = {
    a: host("register", alias=a, agent=a, capabilities=capabilities(a, v))
    for a, v in [("bob", "2.0.4"), ("claude", "2.1.272")]
}
group = host(
    "group", name="native-bob-pair", members=[a["instance"] for a in actors.values()]
)["group"]
context_marker = "BOB_CONTEXT_" + uuid.uuid4().hex[:12]
envs = {}
for agent, actor in actors.items():
    work = base / agent
    work.mkdir()
    (work / ".bob").mkdir()
    cred = work / "credential"
    cred.write_text(actor["token"])
    cred.chmod(0o600)
    wrapper = work / "hook.py"
    wrapper.write_text(
        """import json,sys,pathlib
sys.path.insert(0,"""
        + repr(str(root))
        + """)
from adapters import invoke
raw=json.load(sys.stdin)
with pathlib.Path("""
        + repr(str(work / "events.jsonl"))
        + """).open('a') as f:
 f.write(json.dumps({k:raw[k] for k in ('event','hook_event_name','session_id','turn_id','source','agent_id','agent_type','tool_name','stop_hook_active') if k in raw})+'\\n')
result=invoke("""
        + repr(agent)
        + """,raw,"""
        + repr(str(base / "socket"))
        + ""","""
        + repr(str(cred))
        + """)
if result:
 print(result if isinstance(result,str) else json.dumps(result))
 if """
        + repr(agent)
        + """=='bob' and (raw.get('hook_event_name') or raw.get('event'))=='SessionStart':
  print('Native context verification code: """
        + context_marker
        + """.')
"""
    )
    settings = {
        "hooks": {
            event: [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{sys.executable} {wrapper}",
                            "timeout": 3,
                        }
                    ],
                }
            ]
            for event in EVENTS[agent]
        }
    }
    (work / ".bob/settings.json").write_text(json.dumps(settings))
    (work / "settings.json").write_text(json.dumps(settings))
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "LINCE_AGENT_ID") and not k.startswith("LINCE_MSG_")
    }
    env.update(
        LINCE_MSG_ENDPOINT=str(base / "socket"),
        LINCE_MSG_CREDENTIAL=str(cred),
        TERM="xterm-256color",
    )
    envs[agent] = env
server = Server(base / "socket", store)
thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
thread.start()
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
process = subprocess.Popen(
    [
        "bob",
        "chat",
        "--disable-mcp",
        "--disable-subagents",
        "--auto-approve",
        "--trust",
        "--workspace",
        str(base / "bob"),
    ],
    cwd=base / "bob",
    env=envs["bob"],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    start_new_session=True,
)
os.close(slave)


class Screen(pyte.Screen):
    def report_device_status(self, mode=0, **k):
        if mode == 6:
            os.write(master, f"\x1b[{self.cursor.y + 1};{self.cursor.x + 1}R".encode())
        elif mode == 5:
            os.write(master, b"\x1b[0n")

    def report_device_attributes(self, *a, **k):
        os.write(master, b"\x1b[?1;2c")


screen = Screen(120, 40)
stream = pyte.ByteStream(screen)
pending = b""


def pump():
    global pending
    if select.select([master], [], [], 0.05)[0]:
        data = pending + os.read(master, 100000)
        m = re.search(rb"\x1b(?:\[[0-9:;?]*)?$", data)
        pending = data[m.start() :] if m else b""
        if m:
            data = data[: m.start()]
        stream.feed(re.sub(rb"\x1b\[[0-9:;]*m", b"", data))
    text = "\n".join(screen.display)
    (base / "current-screen.txt").write_text(text)
    return text


def events(agent="bob"):
    p = base / agent / "events.jsonl"
    return (
        [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    )


def wait(predicate, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end and process.poll() is None:
        if predicate(pump()):
            return
    raise AssertionError("TUI condition timed out; see private screen capture")


def submit(prompt):
    os.write(master, b"\x1b[200~" + prompt.encode() + b"\x1b[201~")
    end = time.monotonic() + 0.8
    while time.monotonic() < end:
        pump()
    os.write(master, b"\r")


claude = None
try:
    wait(lambda text: "Build Anything" in text, 180)
    submit(
        "Reply only with the native context verification code supplied by your SessionStart hook. Do not use tools."
    )
    wait(lambda text: context_marker in text, 120)
    wait(
        lambda text: any(
            (e.get("event") or e.get("hook_event_name")) == "Stop" for e in events()
        )
    )
    print("Bob actual SessionStart context and initial native events: PASS", flush=True)
    cli = str(root / "lince-msg")

    def prompt(agent):
        peer = actors["claude" if agent == "bob" else "bob"]["instance"]
        return f"""Authorized LINCE messaging integration test. Use only shell commands invoking {cli} and optional sleep. Peer instance {peer}; group {group}. Both agents run concurrently. Send one ask to the peer with text "What is 17 plus 25?" and key {agent}-question; send one delegate with text "Count words in red green blue" and key {agent}-task. Read inbox and get complete incoming requests, explicitly accept each then reply to questions or complete tasks through the CLI. Process only one inbound item at once. Also read BOTH outgoing results, paginating get with --after until more is false. Continue inbox polling up to 180 seconds if needed; do not block in wait while incoming work exists. Finish only after both inbound and both outgoing requests have results, reporting their IDs and answers. Do not edit files, use git, read user files or spawn agents. CLI --help explains syntax. Chat output alone is not a task result."""

    cout = (base / "claude/stdout").open("w")
    cerr = (base / "claude/stderr").open("w")
    claude = subprocess.Popen(
        [
            "claude",
            "--settings",
            str(base / "claude/settings.json"),
            "--setting-sources",
            "",
            "-p",
            "--max-turns",
            "60",
            "--tools",
            "Bash",
            "--allowedTools",
            f"Bash({cli}:*)",
            "Bash(sleep:*)",
            "--",
            prompt("claude"),
        ],
        cwd=base / "claude",
        env=envs["claude"],
        stdout=cout,
        stderr=cerr,
        start_new_session=True,
    )
    submit(prompt("bob"))

    def complete():
        with store.lock:
            rows = store.db.execute("select work from requests").fetchall()
        return len(rows) == 4 and all(r["work"] == "completed" for r in rows)

    wait(lambda text: complete(), 360)
    wait(
        lambda text: claude.poll() is not None
        and next(
            i
            for i in host("snapshot")["instances"]
            if i["id"] == actors["bob"]["instance"]
        )["readiness"]
        == "input",
        180,
    )
    assert claude.returncode == 0
    print("Bob/Claude real questions and tasks both directions: PASS", flush=True)
    with store.lock:
        rows = [
            dict(r)
            for r in store.db.execute(
                "select id,sender,recipient,kind,delivery,work from requests"
            )
        ]
        audit = [
            dict(r)
            for r in store.db.execute("select request,actor,type,text from events")
        ]
    for actor in actors.values():
        assert {r["kind"] for r in rows if r["sender"] == actor["instance"]} == {
            "question",
            "task",
        }
    for row in rows:
        assert any(
            e["request"] == row["id"]
            and e["actor"] == row["recipient"]
            and e["type"] == "accepted"
            for e in audit
        )
        assert any(
            e["request"] == row["id"]
            and e["actor"] == row["recipient"]
            and e["type"] == ("reply" if row["kind"] == "question" else "complete")
            and e["text"]
            for e in audit
        )
    result = {
        "versions": {"bob": "2.0.4", "claude": "2.1.272"},
        "platform": "Linux",
        "bob_original_tui": True,
        "actors": {actor["instance"]: name for name, actor in actors.items()},
        "bob_final_screen": "\n".join(line.rstrip() for line in screen.display),
        "automatic_intake": False,
        "session_start_context_verified": True,
        "requests": rows,
        "events": audit,
        "native_events": events(),
        "claude_exit": claude.returncode,
    }
    (base / "result.json").write_text(json.dumps(result, indent=2))
finally:
    for child in (process, claude):
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
    os.close(master)
    server.shutdown()
    server.server_close()
    thread.join()
    store.close()
