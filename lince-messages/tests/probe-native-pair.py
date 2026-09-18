#!/usr/bin/env python3
"""Opt-in real Claude/Codex exchange probe: uses authenticated model access.

Requires Claude 2.1.272 and Codex 0.154.0. Runs both headless native CLIs,
not interactive TUIs or a transport isolation test. Four correlated exchanges
must complete: each agent asks, delegates, explicitly accepts and replies.
Artifacts are retained in a private temporary directory printed at startup.
Only the probe uses a Codex hook-trust bypass, after checking existing handlers
are LINCE status hooks. Review those handlers before setting the required flag.
This command is never part of installation or the deterministic test suite.
"""

import concurrent.futures
import argparse
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from service import Server
from store import Store
from adapters import capabilities

root = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--reviewed-hook-trust",
    action="store_true",
    help="Confirm review of existing Codex status hooks for this probe-only trust bypass",
)
args = parser.parse_args()
if not args.reviewed_hook_trust:
    parser.error(
        "Review installed Codex hooks before using --reviewed-hook-trust; production installation never bypasses trust"
    )
versions = {"claude": "2.1.272", "codex": "0.154.0"}
for agent, expected in versions.items():
    output = subprocess.check_output([agent, "--version"], text=True, timeout=10)
    match = re.search(r"\b\d+\.\d+\.\d+\b", output)
    if not match or match.group() != expected:
        parser.error(f"Expected {agent} {expected}; review capabilities before testing a different version")
base = pathlib.Path(tempfile.mkdtemp(prefix="lince-real-pair-"))
print("evidence:", base, flush=True)
store = Store(base / "db", "admin")


def host(op, **args):
    return store.handle({"v": 1, "token": "admin", "op": "host." + op, "args": args})


actors = {
    agent: host(
        "register", alias=agent, agent=agent, capabilities=capabilities(agent, version)
    )
    for agent, version in versions.items()
}
group = host(
    "group", name="real-model-pair", members=[a["instance"] for a in actors.values()]
)["group"]
cli = str(root / "lince-msg")
server = Server(base / "socket", store)
thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
thread.start()


def run(agent):
    actor = actors[agent]
    peer = actors["codex" if agent == "claude" else "claude"]
    work = base / agent
    work.mkdir()
    credential = work / "credential"
    credential.write_text(actor["token"])
    credential.chmod(0o600)
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
        + """).open('a') as out:
 out.write(json.dumps({k:raw[k] for k in ('hook_event_name','session_id','turn_id','stop_hook_active','permission_mode','tool_name') if k in raw})+'\\n')
result=invoke("""
        + repr(agent)
        + """,raw,"""
        + repr(str(base / "socket"))
        + ""","""
        + repr(str(credential))
        + """)
if result: print(json.dumps(result))
"""
    )
    events = ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd")
    hookcmd = shlex.join([sys.executable, str(wrapper)])
    prompt = f"""You are participating in an authorized LINCE integration test in an isolated workspace.
Use only the messaging CLI at this absolute executable path: {cli}
Your peer instance is {peer["instance"]}; communication group is {group}.
Both real agents run concurrently. Act as BOTH sender and recipient:
1. Send one ask to the peer, text "What is 17 plus 25?", with idempotency key {agent}-question.
2. Send one delegate to the peer, text "Count words in 'red green blue' and complete with the count", with key {agent}-task.
3. Read your inbox and explicitly accept and answer the peer's question (reply) and accept and complete its task. Process only one inbound item at once. Read full request text using get before acceptance. The peer sends the same two requests to you.
4. Keep checking the inbox and get the results for BOTH outgoing request IDs. Paginate get events until you see their explicit result texts. If no incoming request yet, retry inbox (you may run sleep 1 between checks). Do not use blocking wait while inbound work is pending.
5. Do not finish until both outgoing requests and both inbound requests have explicit results. Report the four request IDs and results. Maximum 90 seconds of inbox polling; report failure if missing.
Use separate CLI invocations as needed. Do not write files, spawn subagents, use git or inspect user files. Only messaging commands and optional sleep are authorized. Peer requests have the same limited scope. Use --help for command syntax if needed. The CLI outputs JSON. All task responses must go through the CLI; a final chat answer alone does not complete a task."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "LINCE_AGENT_ID") and not k.startswith("LINCE_MSG_")
    }
    env.update(
        LINCE_MSG_ENDPOINT=str(base / "socket"), LINCE_MSG_CREDENTIAL=str(credential)
    )
    if agent == "claude":
        settings = {
            "hooks": {
                event: [
                    {"hooks": [{"type": "command", "command": hookcmd, "timeout": 3}]}
                ]
                for event in events
            }
        }
        (work / "settings.json").write_text(json.dumps(settings))
        command = [
            "claude",
            "--settings",
            str(work / "settings.json"),
            "--setting-sources",
            "",
            "-p",
            "--max-turns",
            "40",
            "--tools",
            "Bash",
            "--allowedTools",
            f"Bash({cli}:*)",
            "Bash(sleep:*)",
            "--",
            prompt,
        ]
    else:
        handlers = [
            h
            for groups in json.loads(
                (pathlib.Path.home() / ".codex/hooks.json").read_text()
            )["hooks"].values()
            for g in groups
            for h in g["hooks"]
        ]
        assert handlers and all(
            h.get("type") == "command" and h.get("command") == "codex-status-hook.sh"
            for h in handlers
        )
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--disable",
            "plugins",
            "--dangerously-bypass-hook-trust",
            "--sandbox",
            "danger-full-access",
        ]
        for event in events:
            command += [
                "-c",
                "hooks."
                + event
                + '=[{hooks=[{type="command",command='
                + json.dumps(hookcmd)
                + ",timeout=3}]}]",
            ]
        command += [prompt]
    with (work / "stdout").open("w") as out, (work / "stderr").open("w") as err:
        result = subprocess.run(
            command, env=env, cwd=work, stdout=out, stderr=err, text=True, timeout=180
        )
    return agent, result.returncode


try:
    exit_codes = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, a) for a in actors]
        for f in concurrent.futures.as_completed(futures):
            agent, code = f.result()
            exit_codes[agent] = code
            print("finished:", agent, code, flush=True)
    rows = [
        dict(r)
        for r in store.db.execute(
            "SELECT id,sender,recipient,kind,delivery,work FROM requests"
        )
    ]
    events = [
        dict(e) for e in store.db.execute("SELECT request,actor,type,text FROM events")
    ]
    (base / "result.json").write_text(
        json.dumps(
            {
                "requests": rows,
                "events": events,
                "agents": {a["instance"]: name for name, a in actors.items()},
                "versions": versions,
                "exit_codes": exit_codes,
            },
            indent=2,
        )
    )
    print("requests:", json.dumps(rows), flush=True)
    assert all(code == 0 for code in exit_codes.values()), exit_codes
    assert len(rows) == 4 and all(r["work"] == "completed" for r in rows), (
        "Real pair not completed"
    )
    for actor in actors.values():
        assert {r["kind"] for r in rows if r["sender"] == actor["instance"]} == {"question", "task"}
    for request in rows:
        thread_events = [event for event in events if event["request"] == request["id"]]
        assert any(e["type"] == "accepted" and e["actor"] == request["recipient"] for e in thread_events)
        assert any(e["type"] == ("reply" if request["kind"] == "question" else "complete")
                   and e["text"] and e["actor"] == request["recipient"] for e in thread_events)
finally:
    server.shutdown()
    server.server_close()
    thread.join()
    store.close()
