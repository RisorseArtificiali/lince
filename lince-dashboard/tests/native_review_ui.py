"""Opt-in native TUI review demonstration; never part of deterministic tests.

Uses existing authenticated accounts. The test driver submits human prompts in
its own disposable Zellij session; product messaging never writes terminal input.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tomllib


VERSIONS = {"claude": "2.1.272", "codex": "0.154.0"}
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "PermissionRequest", "Stop", "SessionEnd")


def prepare(work, fixture):
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    config = tomllib.loads((codex_home / "config.toml").read_text())
    assert set(config.get("hooks", {})) <= {"state"}, "Review inline Codex hooks before probe"
    handlers = [h for groups in json.loads((codex_home / "hooks.json").read_text())["hooks"].values()
                for group in groups for h in group["hooks"]]
    assert all(h.get("type") == "command" and h.get("command") == "codex-status-hook.sh"
               for h in handlers), "Probe only permits reviewed existing LINCE status hooks"
    (work / "review.py").write_text("def inclusive_sum(start, end):\n    return sum(range(start, end))\n")
    for agent, expected in VERSIONS.items():
        executable = shutil.which(agent)
        assert executable, f"Missing {agent}"
        version = subprocess.check_output([executable, "--version"], text=True, timeout=10)
        assert re.search(r"\b" + re.escape(expected) + r"\b", version), version
        (work / agent).symlink_to(executable)
        hook = shlex.join([str(work / "lince-msg-hook"), agent])
        # Authentication stays in the existing native configuration. Broker
        # provisioning uses the isolated parent HOME before this child override.
        # Unset the legacy status identity to avoid updating user's pane files.
        command = ["/usr/bin/env", "-u", "LINCE_AGENT_ID", "-u", "CLAUDECODE",
                   f"HOME={home}", f"CODEX_HOME={codex_home}", executable]
        if agent == "claude":
            settings = {"hooks": {event: [{"hooks": [{"type": "command", "command": hook,
                                                       "timeout": 3}]}] for event in EVENTS}}
            path = work / "claude-settings.json"
            path.write_text(json.dumps(settings))
            command += ["--settings", str(path), "--setting-sources", "", "--tools", "Bash",
                        "--allowedTools", f"Bash({work / 'lince-msg'} *)", "Bash(sleep *)",
                        "Bash(python3 *)", "--", "Reply exactly REVIEW_READY. Do not use tools."]
        else:
            command += ["--no-alt-screen", "--disable", "plugins", "--dangerously-bypass-hook-trust",
                        "--sandbox", "read-only", "-a", "on-request"]
            for name in config.get("mcp_servers", {}):
                assert re.fullmatch(r"[A-Za-z0-9_-]+", name), "Unsupported MCP configuration name"
                command += ["-c", f"mcp_servers.{name}.enabled=false"]
            for event in EVENTS:
                command += ["-c", f"hooks.{event}=[{{hooks=[{{type=\"command\",command="
                            + json.dumps(hook) + ",timeout=3}]}]"]
            command += ["Reply exactly REVIEW_READY. Do not use tools."]
        fixture["agents"][agent] = {"display_name": agent, "short_label": agent.upper()[:3],
            "color": "green", "command": command, "sandboxed": False,
            "dashboard": {"pane_title_pattern": agent, "has_native_hooks": True}}
    return fixture


def check_review(work, session, cli, wait_for, key, panes, visible, env, terminal, evidence):
    def host(op, **args):
        result = subprocess.run([str(work / "lince-msg-host"), "--session", session,
                                 "request", op, "--json", json.dumps(args)],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    def screen(ps, name):
        pane = ps.get(name)
        if not pane:
            return ""
        x, y = pane["pane_x"], pane["pane_y"]
        return "\n".join(line[x:x + pane["pane_columns"]]
                         for line in terminal.display[y:y + pane["pane_rows"]])

    wait_for(lambda ps: len(host("snapshot")["instances"]) == 2, timeout=60)
    actors = {i["agent"]: i for i in host("snapshot")["instances"]}
    assert set(actors) == {"claude", "codex"}, actors.keys()
    group = host("group", name="Native review", members=[i["id"] for i in actors.values()])["group"]
    # Initial native turns must finish before submitting the next human input.
    wait_for(lambda ps: all(i["readiness"] == "input" for i in host("snapshot")["instances"]), timeout=120)
    print("native review: both original TUIs registered and ready", flush=True)

    def focused(agent):
        return lambda ps: any(not p["is_plugin"] and str(p["id"]) == actors[agent]["pane_ref"]
                              and p["is_focused"] for p in ps.values())

    def submit(agent, number, prompt):
        key(b"\x1b" + str(number).encode())
        wait_for(focused(agent))
        assert cli(["-s", session, "action", "write-chars", prompt])[0] == 0
        # The trailing sentinel proves the entire prompt rendered before Enter.
        wait_for(lambda ps: "END_REVIEW_PROMPT" in "".join("".join(terminal.display).split()))
        key(b"\r")

    msg = str(work / "lince-msg")
    independent = work / "independent-result.txt"
    receipt = work / "review-receipt.txt"
    sender_prompt = (
        f"Authorized integration test. Use only Bash with the CLI {msg}. "
        f"Ask peer {actors['codex']['id']} in group {group} to review {work / 'review.py'} "
        "for correctness, using --key native-review and text beginning NATIVE_REVIEW. "
        f"After ask returns, continue independent work: compute 17+25 using python3 and write "
        f"the computed number to {independent}. Do not wait for the peer yet. "
        "Report the request ID and stop. END_REVIEW_PROMPT")
    submit("claude", 1, sender_prompt)
    wait_for(lambda ps: bool(host("snapshot")["requests"]), timeout=120)
    request = host("snapshot")["requests"][0]["id"]
    wait_for(lambda ps: "Mail 1" in screen(ps, "lince-attention"))
    assert focused("claude")({p["title"]: p for p in panes()})
    wait_for(lambda ps: independent.exists() and independent.read_text().strip() == "42", timeout=120)
    assert host("get", request=request)["work"] == "pending"
    print("native review: sender continued independent work with review pending", flush=True)

    recipient_prompt = (
        f"Authorized integration test. Use the shell and {msg} to get request {request}, "
        "read it, then explicitly accept it. Review only the requested Python file, without editing. "
        "After acceptance run sleep 20 so the human can observe active provenance. "
        f"Then reply to {request} through the CLI with your concrete finding and a failing example, "
        "using --key native-review-result. Stop after replying. END_REVIEW_PROMPT")
    submit("codex", 2, recipient_prompt)
    # Focus the sender again; peer processing must not reveal or refocus Codex.
    key(b"\x1b1")
    wait_for(focused("claude"))
    wait_for(lambda ps: host("get", request=request)["work"] == "active", timeout=120)
    wait_for(lambda ps: "Work 1" in screen(ps, "lince-attention"))
    current = {p["title"]: p for p in panes()}
    assert focused("claude")(current)
    assert next(p for p in current.values() if not p["is_plugin"]
                and str(p["id"]) == actors["codex"]["pane_ref"])["is_suppressed"]
    key(b"\x1b2")
    wait_for(focused("codex"))
    current = wait_for(lambda ps: request[:8] in screen(ps, "lince-attention")
                       and "ask" in screen(ps, "lince-attention"))
    provenance = screen(current, "lince-attention")
    wait_for(lambda ps: host("get", request=request)["work"] == "completed", timeout=120)
    print("native review: real peer accepted/replied; hidden-pane focus and provenance verified", flush=True)
    submit("claude", 1, f"Use Bash with {msg} get {request}; paginate events if needed. "
           "Read the peer's review, then use python3 to write the exact correlated request ID "
           f"and the peer's concrete finding (including the faulty expression and failing example) into {receipt}. "
           "End with a brief summary. END_REVIEW_PROMPT")
    wait_for(lambda ps: receipt.exists() and request in receipt.read_text()
             and "range" in receipt.read_text()
             and all(i["readiness"] == "input" for i in host("snapshot")["instances"]), timeout=120)
    key(b"\x1bd")
    wait_for(visible("lince-dialog", True))
    key(b"m")
    wait_for(lambda ps: "NATIVE_REVIEW" in screen(ps, "lince-dialog"))
    wait_for(lambda ps: "Cancel does not undo edits." in screen(ps, "lince-dialog"))
    key(b"\r")
    wait_for(lambda ps: "work completed" in screen(ps, "lince-dialog"))
    current = wait_for(lambda ps: "Cancel does not undo edits." in screen(ps, "lince-dialog")
                       and "More events available" not in screen(ps, "lince-dialog"))
    thread_header = screen(current, "lince-dialog")
    # The complete result must also be inspectable in the actual dialog, beyond
    # the header and first event that arrive in the initial asynchronous page.
    for _ in range(4):
        if "range(start" in screen(current, "lince-dialog"):
            break
        previous = screen(current, "lince-dialog")
        key(b"\x1b[6~")
        current = wait_for(lambda ps: screen(ps, "lince-dialog") != previous)
    assert "range(start" in screen(current, "lince-dialog"), "Review result missing from Alt+d"
    result = host("get", request=request)
    events = list(result["events"])
    page = result
    while page["more"]:
        page = host("get", request=request, after=page["cursor"])
        events.extend(page["events"])
    assert any(e["type"] == "reply" and "range" in e["text"] for e in events)
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "native-review.json").write_text(json.dumps({
        "versions": VERSIONS, "platform": "Linux", "original_tuis": True,
        "automatic_wakeup": False, "request": result, "events": events,
        "independent_result": independent.read_text(), "sender_receipt": receipt.read_text(),
        "status_line": provenance,
        "thread_header": thread_header, "thread_screen": screen(current, "lince-dialog"),
        "sender_continued_while_pending": True, "hidden_peer_did_not_steal_focus": True,
        "sender_received_correlated_review": True,
    }, indent=2) + "\n")
    print(f"native review: integrated status line and Alt+d PASS; evidence: {evidence}", flush=True)
