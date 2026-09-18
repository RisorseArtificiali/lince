#!/usr/bin/env python3
"""Exercise real Zellij plugin roles in disposable sessions.

Requires Zellij >= 0.45.1 and a built WASM. Uses disposable sessions/config/cache.
Ordinary smoke tests use harmless fixture agents. The explicit native-review
option uses authenticated Claude/Codex TUIs and saves review evidence.
  python3 tests/check-ui-session.py --zellij /path/to/zellij
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import runpy
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = runpy.run_path(str(ROOT / "lince-dashboard-launch"))


def check(zellij, wasm, preset, messaging=False, native_review=None):
    version = subprocess.check_output([zellij, '--version'], text=True).strip()
    match = re.fullmatch(r'zellij (\d+)\.(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (0, 45, 1):
        raise SystemExit(f'Zellij >= 0.45.1 required; found {version} at {zellij}')
    with tempfile.TemporaryDirectory(prefix="lince-ui-test-") as directory:
        work = Path(directory)
        layout_name = "dashboard-statusline" if preset == "statusline" else "dashboard-tiled"
        text = LAUNCHER["presentation_layout"](
            LAUNCHER["sidebar_layout"]((ROOT / "layouts" / f"{layout_name}.kdl").read_text(), 15), preset, True, True)
        text = text.replace("file:~/.config/zellij/plugins/lince-dashboard.wasm", f"file:{wasm}")
        text = text.replace("~/.config/lince-dashboard/config.toml", str(work / "config.toml"))
        text = text.replace('command "lince-viewport-placeholder"', 'command "sh"')
        text += '\ndefault_shell "/bin/sh"\npane_frames false\nauto_layout false\nshow_startup_tips false\nshow_release_notes false\n'
        (work / "layout.kdl").write_text(text)
        (work / "config.toml").write_text('[dashboard]\nagent_layout="tiled"\ncompact=true\nsandbox_command="/bin/false"\n')
        # Ordinary smoke runs launch only harmless sleep processes.
        fixture = {"agents": {"fixture": {"display_name": "Fixture", "short_label": "FIX",
            "color": "green", "command": ["/bin/sleep", "600"],
            "dashboard": {"pane_title_pattern": "sleep", "has_native_hooks": True}}}}
        if native_review:
            from native_review_ui import prepare
            fixture = prepare(work, fixture)
        (work / "lince-config").write_text("#!/bin/sh\ncat <<'FIXTURE'\n" + json.dumps(fixture) + "\nFIXTURE\n")
        (work / "lince-config").chmod(0o755)
        shutil.copyfile(ROOT / "tests/voice-fixture.py", work / "lince-voice")
        (work / "lince-voice").chmod(0o755)
        (work / ".lince-dashboard").write_text(json.dumps({"version": 3, "next_agent_id": 0,
            "agents": [{"name": f"fixture{i}",
                        "agent_type": ({1: "claude", 2: "codex"}.get(i, "fixture") if native_review else "fixture"),
                        "project_dir": str(ROOT.parent if native_review else work)}
                       for i in (1, 2, 3)]}))
        (work / "session.kdl").write_text((ROOT / "zellij-config/config.kdl").read_text()
            + f'\nenv {{ PATH "{work}:{Path(zellij).parent}:/usr/bin:/bin"; }}\n')
        permissions = work / "cache/zellij/permissions.kdl"
        permissions.parent.mkdir(parents=True)
        permissions.write_text(f'"{wasm}" {{\n RunCommands\n ReadApplicationState\n ReadCliPipes\n'
                               ' WriteToStdin\n ChangeApplicationState\n OpenTerminalsOrPlugins\n'
                               ' MessageAndLaunchOtherPlugins\n}\n')
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
        terminal = None
        if messaging:
            import pyte
            class ObservationScreen(pyte.Screen):
                def report_device_status(self, *args, **kwargs):
                    pass

                def report_device_attributes(self, *args, **kwargs):
                    pass

            terminal = ObservationScreen(100, 32)
            terminal_stream = pyte.ByteStream(terminal)
        env = {key: value for key, value in os.environ.items() if not key.startswith("ZELLIJ")}
        env.update(TERM="xterm-256color", XDG_CACHE_HOME=str(work / "cache"),
                   PATH=f"{Path(zellij).parent}:{work}:{os.environ['PATH']}")
        if messaging:
            env.update(HOME=str(work), LINCE_MESSAGES_BIN_DIR=str(work),
                       LINCE_MESSAGES_INSTALL_DIR=str(work / "messages"))
            env.pop("CODEX_HOME", None)
            subprocess.run(["bash", str(ROOT.parent / "lince-messages/install.sh")],
                           env=env, check=True, capture_output=True)
        session = f"lince-ui-test-{uuid.uuid4().hex[:10]}"
        process = subprocess.Popen(
            [zellij, "--config", str(work / "session.kdl"), "--config-dir", str(work),
             "--data-dir", str(work / "data"), "--layout", str(work / "layout.kdl"),
             "options", "--session-name", session], cwd=work, env=env,
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        terminal_pending = b''

        def pump():
            nonlocal terminal_pending
            # Drain the PTY: one read per CLI query can back-pressure Zellij's
            # renderer and delay keyboard events when the voice meter updates.
            ready = select.select([master], [], [], 0.01)[0]
            drained = 0
            while ready and drained < 1024 * 1024:
                try:
                    chunk = os.read(master, 100000)
                    if not chunk:
                        break
                    if terminal is not None:
                        # Zellij emits colon-form truecolor SGR, which pyte 0.8
                        # does not parse. Ignore styling, retaining all cursor
                        # and erase controls and incomplete sequences across reads.
                        data = terminal_pending + chunk
                        partial = re.search(rb'\x1b(?:\[[0-9:;?]*)?$', data)
                        terminal_pending = data[partial.start():] if partial else b''
                        if partial:
                            data = data[:partial.start()]
                        terminal_stream.feed(re.sub(rb'\x1b\[[0-9:;]*m', b'', data))
                    drained += len(chunk)
                except OSError:
                    break
                ready = select.select([master], [], [], 0)[0]

        def cli(arguments):
            command = subprocess.Popen([zellij, *arguments], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, env=env)
            deadline = time.monotonic() + 10
            while True:
                pump()
                try:
                    stdout, stderr = command.communicate(timeout=0.01)
                    return command.returncode, stdout, stderr
                except subprocess.TimeoutExpired:
                    if time.monotonic() > deadline:
                        command.kill()
                        command.communicate()
                        raise AssertionError(f"Zellij command timed out: {arguments}")

        def panes():
            status, stdout, _ = cli(["-s", session, "action", "list-panes", "--json", "--all"])
            # Zellij can acknowledge startup queries before returning a manifest.
            if status != 0 or not stdout.strip():
                return []
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as error:
                # Before the new socket exists, Zellij lists existing sessions
                # with exit code zero instead of returning a pane manifest.
                if "[Created " in stdout:
                    return []
                raise AssertionError(f"Unexpected list-panes response: {stdout[:300]!r}") from error

        def wait_for(predicate, timeout=15):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                pump()
                current = {pane["title"]: pane for pane in panes()}
                if predicate(current):
                    return current
                if process.poll() is not None:
                    break
                next_poll = time.monotonic() + 0.1
                while time.monotonic() < next_poll:
                    pump()
            fields = ("title", "is_suppressed", "is_focused", "pane_x", "pane_y", "pane_columns", "pane_rows", "terminal_command")
            summary = [{k: p[k] for k in fields} for p in panes()]
            if terminal is not None:
                print('\n'.join(terminal.display), flush=True)
            raise AssertionError(f"{preset}: UI condition timed out; panes={summary}")

        def floating_visible():
            status, stdout, _ = cli(["-s", session, "action", "list-tabs", "--json", "--state"])
            return status == 0 and any(tab["are_floating_panes_visible"] for tab in json.loads(stdout))

        def client_focus(pane_id):
            status, stdout, _ = cli(["-s", session, "action", "list-clients"])
            return status == 0 and any(len(row.split()) > 1 and row.split()[1] == pane_id for row in stdout.splitlines()[1:])

        def visible(name, expected):
            return lambda ps: (name in ps and (not ps[name]["is_suppressed"]) == expected
                and (name != "lince-dialog" or not expected
                     or (ps[name]["is_focused"] and floating_visible() and client_focus(f"plugin_{ps[name]['id']}"))))

        def key(data):
            # Encode complete key events as a terminal with CSI-u support does.
            if data.startswith(b"\x1b") and len(data) == 2:
                data = f"\x1b[{data[1]};3u".encode()
            elif len(data) == 1:
                data = ("\x1b[108;5u" if data == b"\x0c" else f"\x1b[{data[0]}u").encode()
            os.write(master, data)

        try:
            # Let the first client attach before issuing CLI queries; Zellij
            # 0.45.1 can panic when an action races initial client registration.
            attach_deadline = time.monotonic() + 0.5
            while time.monotonic() < attach_deadline and process.poll() is None:
                pump()
            initial = wait_for(lambda ps: visible("lince-dialog", False)(ps)
                and visible("lince-controller", preset != "statusline")(ps)
                and "lince-viewport" in ps and sum("fixture" in name for name in ps) == 3
                and sum("fixture" in name and ps[name]["is_suppressed"] for name in ps) >= 2)
            if preset == "classic":
                from messaging_ui_smoke import check_messages
                assert 'lince-attention' not in initial
                check_messages(work, session, cli, wait_for, key, panes, visible, env, terminal, attention=False)
                print('classic: original Zellij chrome retained; Alt+d messaging controls OK')
                return
            assert initial["lince-attention"]["pane_rows"] == 2
            assert initial["lince-attention"]["pane_y"] == 30
            if native_review:
                from native_review_ui import check_review
                check_review(work, session, cli, wait_for, key, panes, visible, env,
                             terminal, native_review)
                return
            identities = {(p["id"], p["is_plugin"]) for p in panes()}
            assert len(identities) == 7
            if messaging:
                from messaging_ui_smoke import check_messages
                check_messages(work, session, cli, wait_for, key, panes, visible, env, terminal)
            viewport = initial["lince-viewport"]
            if preset == "statusline":
                assert viewport["pane_columns"] == 100, viewport
            # Global list/info/help/wizard all open one bordered passive popup.
            for shortcut in (b"\x1bd", b"\x1bi", b"\x1bh", b"\x1bn", b"\x1bv"):
                key(shortcut)
                shown = wait_for(visible("lince-dialog", True))
                assert shown["lince-viewport"]["pane_columns"] == viewport["pane_columns"]
                assert not shown["lince-attention"]["is_suppressed"]
                assert shown["lince-dialog"]["pane_y"] + shown["lince-dialog"]["pane_rows"] <= 30
                key(b"\x1b")
                wait_for(visible("lince-dialog", False))
            # Configure once, then global PTT inserts into the visible shell.
            def voice_state(expected):
                return lambda ps: (work / "lince-voice.json").exists() and json.loads(
                    (work / "lince-voice.json").read_text())["status"] == expected

            # Focus the placeholder shell before opening the configuration popup.
            assert cli(["-s", session, "action", "hide-floating-panes"])[0] == 0
            focus_result = cli(["-s", session, "action", "focus-pane-id", f'terminal_{viewport["id"]}'])
            assert focus_result[0] == 0 or "already focused" in focus_result[2], focus_result
            wait_for(lambda ps: ps["lince-viewport"]["is_focused"])
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"s")
            wait_for(lambda ps: (work / "lince-voice.json").exists() and json.loads((work / "lince-voice.json").read_text())["settings"]["configured"])
            key(b"a")
            wait_for(voice_state("listening"))
            key(b"m")
            wait_for(voice_state("muted"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"m")
            wait_for(voice_state("listening"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            # Ctrl+Space (NUL) starts; Alt+t stops the same recording.
            os.write(master, b"\x00")
            wait_for(voice_state("recording"))
            key(b"\x1bt")
            wait_for(voice_state("listening"))
            wait_for(lambda ps: not json.loads((work / "lince-voice.json").read_text())["events"])
            wait_for(lambda ps: "VOICE_FIXTURE_TEXT" in cli(["-s", session, "action", "dump-screen", "--pane-id", str(viewport["id"])])[1])
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"x")
            wait_for(voice_state("stopped"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            # Voice shortcuts are available in locked mode too.
            key(b"\x0c")
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"a")
            wait_for(voice_state("listening"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            key(b"\x1bt")
            wait_for(voice_state("recording"))
            # Enhanced-keyboard Ctrl+Space also works in locked mode.
            key(b"\x1b[32;5u")
            wait_for(voice_state("listening"))
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"x")
            wait_for(voice_state("stopped"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            key(b"\x1bh")
            wait_for(visible("lince-dialog", True))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            key(b"\x0c")
            active_fixture = "fixture1"

            def focused_fixture(ps):
                return next((p for name, p in ps.items() if active_fixture in name
                             and not p["is_suppressed"] and p["is_focused"]), None)

            def agent_fills_viewport(ps):
                agent = focused_fixture(ps)
                viewport = ps.get("lince-viewport")
                if not (agent and viewport and all(agent[field] == viewport[field] for field in
                    ("pane_x", "pane_y", "pane_columns", "pane_rows"))):
                    return False
                if any(not p["is_suppressed"] for name, p in ps.items()
                       if "fixture" in name and active_fixture not in name):
                    return False
                # Unsuppressed floating panes can still be hidden as a layer.
                status, stdout, _ = cli(["-s", session, "action", "list-tabs", "--json", "--state"])
                return status == 0 and any(tab["are_floating_panes_visible"] for tab in json.loads(stdout))

            key(b"\x1b1")
            agent_panes = wait_for(agent_fills_viewport)
            agent_id = focused_fixture(agent_panes)["id"]
            key(b"\x1bt")
            wait_for(voice_state("recording"))
            key(b"\x1bt")
            wait_for(voice_state("listening"))
            wait_for(lambda ps: "VOICE_FIXTURE_TEXT" in cli(["-s", session, "action", "dump-screen", "--pane-id", str(agent_id)])[1])
            key(b"\x1bv")
            wait_for(visible("lince-dialog", True))
            key(b"x")
            wait_for(voice_state("stopped"))
            key(b"\x1b")
            wait_for(visible("lince-dialog", False))
            wait_for(agent_fills_viewport)
            # Toggle both ways; the controller and auxiliary pane must disappear.
            for turn, expected in enumerate((preset != "minimal", preset == "minimal") * 3):
                number = (1, 2, 3)[turn // 2]
                active_fixture = f"fixture{number}"
                key(b"\x1b" + str(number).encode())
                wait_for(agent_fills_viewport)
                key(b"\x1bs")
                changed = wait_for(lambda ps: visible("lince-controller", expected)(ps)
                    and "lince-viewport" in ps and (ps["lince-viewport"]["pane_columns"] < 100) == expected
                    and (not expected or (ps["lince-controller"]["pane_y"] == 0
                        and ps["lince-viewport"]["pane_columns"] == 85)))
                assert {(p["id"], p["is_plugin"]) for p in panes()} == identities
                assert "lince-sidebar-aux" not in changed
                if expected:
                    assert changed["lince-controller"]["pane_x"] == 0, changed
                    assert changed["lince-controller"]["pane_y"] == 0, changed
                    assert changed["lince-controller"]["pane_rows"] == changed["lince-viewport"]["pane_rows"], changed
                    assert changed["lince-viewport"]["pane_columns"] == 85, changed
                # The visible agent must resize immediately, before refocusing it.
                wait_for(agent_fills_viewport)
                for number in (3, 2, 1):
                    active_fixture = f"fixture{number}"
                    key(b"\x1b" + str(number).encode())
                    wait_for(agent_fills_viewport)
                key(b"\x1bd")
                wait_for(visible("lince-dialog", True))
                key(b"\x1b")
                wait_for(visible("lince-dialog", False))
            sidebar_shown = preset == "minimal"
            bar_mode = 2
            bar_shown = True
            for shortcut in (b"\x1bb", b"\x1bs", b"\x1bb", b"\x1bs", b"\x1bb", b"\x1bb") * 2:
                if shortcut == b"\x1bb":
                    bar_mode = (bar_mode + 1) % 4
                    bar_shown = bar_mode != 0
                else:
                    sidebar_shown = not sidebar_shown
                key(shortcut)
                wait_for(lambda ps: visible("lince-attention", bar_shown)(ps)
                    and visible("lince-controller", sidebar_shown)(ps)
                    and ps.get("lince-viewport", {}).get("pane_columns") == (85 if sidebar_shown else 100)
                    and ps.get("lince-viewport", {}).get("pane_rows") == (30 if bar_shown else 32))
                wait_for(agent_fills_viewport)
                # Agent navigation and geometry must work even with both hidden.
                for number in (2, 1):
                    active_fixture = f"fixture{number}"
                    key(b"\x1b" + str(number).encode())
                    wait_for(agent_fills_viewport)
                assert {(p["id"], p["is_plugin"]) for p in panes()} == identities
            # Status bar shortcut also works while Zellij is locked.
            key(b"\x0c")
            for shown in (True, False, True, True):
                key(b"\x1bb")
                wait_for(visible("lince-attention", shown))
                wait_for(agent_fills_viewport)
            key(b"\x0c")
            state_path = work / ".lince-dashboard"
            original = '{"version":3,"agents":[],"next_agent_id":73,"session_defaults":null}'
            if preset == "statusline":
                # Save a view different from the CLI defaults.
                key(b"\x1bs")
                wait_for(visible("lince-controller", True))
                key(b"\x1bb")  # full -> agents
                for _ in range(5):
                    pump()
                key(b"\x1bb")  # agents -> hidden
                wait_for(visible("lince-attention", False))
                key(b"\x1bb")  # hidden -> summary
                wait_for(visible("lince-attention", True))
                wait_for(agent_fills_viewport)
                # Save/quit is global, including locked mode.
                key(b"\x0c")
                key(b"\x1bq")
            else:
                state_path.write_text(original)
                key(b"\x1bd")
                wait_for(visible("lince-dialog", True))
                key(b"q")
            deadline = time.monotonic() + 15
            while process.poll() is None and time.monotonic() < deadline:
                pump()
            assert process.poll() is not None, "Quit shortcut did not close the session"
            if preset == "statusline":
                saved = json.loads(state_path.read_text())
                assert len(saved["agents"]) == 3 and saved["version"] == 3
                assert saved["view"] == {"sidebar_visible": True, "statusbar_mode": "summary"}
                # Start again from the same project, with the statusline preset.
                # Repeat with both bars hidden to cover suppressed initialization.
                for expected_sidebar, expected_mode in ((True, "summary"), (False, "agents"), (False, "hidden")):
                    os.close(master)
                    master, slave = pty.openpty()
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
                    session = f"lince-ui-test-{uuid.uuid4().hex[:10]}"
                    process = subprocess.Popen(
                        [zellij, "--config", str(work / "session.kdl"), "--config-dir", str(work),
                         "--data-dir", str(work / "data"), "--layout", str(work / "layout.kdl"),
                         "options", "--session-name", session], cwd=work, env=env,
                        stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
                    os.close(slave)
                    wait_for(lambda ps: visible("lince-controller", expected_sidebar)(ps)
                        and visible("lince-attention", expected_mode != "hidden")(ps)
                        and sum("fixture" in name for name in ps) == 3
                        and ps.get("lince-viewport", {}).get("pane_columns") == (85 if expected_sidebar else 100)
                        and ps.get("lince-viewport", {}).get("pane_rows") == (32 if expected_mode == "hidden" else 30))
                    active_fixture = "fixture2"
                    key(b"\x1b2")
                    wait_for(agent_fills_viewport)
                    if expected_sidebar:
                        key(b"\x1bs")
                        wait_for(visible("lince-controller", False))
                        key(b"\x1bb")  # summary -> full
                        for _ in range(5):
                            pump()
                        key(b"\x1bb")  # full -> agents
                        wait_for(visible("lince-attention", True))
                        wait_for(agent_fills_viewport)
                    elif expected_mode == "agents":
                        key(b"\x1bb")  # agents -> hidden
                        wait_for(visible("lince-attention", False))
                        wait_for(agent_fills_viewport)
                    key(b"\x1bq")
                    deadline = time.monotonic() + 15
                    while process.poll() is None and time.monotonic() < deadline:
                        pump()
                    assert process.poll() is not None
                    assert json.loads(state_path.read_text())["view"] == {
                        "sidebar_visible": False, "statusbar_mode": "agents" if expected_sidebar else "hidden"}
            else:
                assert state_path.read_text() == original, "Quit without save modified previous state"
            print(f"{preset}: voice controls and shell delivery, global popups, sidebar/status-bar combinations, agent geometry and {'save/quit' if preset == 'statusline' else 'quit without save'} OK")
        finally:
            try:
                cli(["kill-session", session])
            finally:
                process.terminate()
                os.close(master)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                if messaging:
                    subprocess.run(["python3", str(work / "messages/maintenance.py")],
                                   env=env, check=True, timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zellij", default=shutil.which("zellij"))
    parser.add_argument("--wasm", type=Path,
                        default=ROOT / "plugin/target/wasm32-wasip1/release/lince-dashboard.wasm")
    parser.add_argument("--messaging", action="store_true", help="Also exercise a real isolated mailbox and its UI")
    parser.add_argument("--native-review-evidence", type=Path,
                        help="Opt-in authenticated Claude/Codex TUI review; save sanitized evidence in this directory")
    parser.add_argument("--reviewed-hook-trust", action="store_true",
                        help="Confirm review of existing Codex status hooks for the native probe's invocation-only bypass")
    args = parser.parse_args()
    if not args.zellij or not args.wasm.exists():
        parser.error("Zellij and a built WASM are required")
    if args.native_review_evidence:
        if not args.reviewed_hook_trust:
            parser.error("Native review requires --reviewed-hook-trust after reviewing existing Codex hooks")
        check(str(Path(args.zellij).resolve()), args.wasm.resolve(), "statusline", True,
              args.native_review_evidence.resolve())
        raise SystemExit(0)
    for preset in (("statusline", "minimal", "classic") if args.messaging else ("statusline", "minimal")):
        check(str(Path(args.zellij).resolve()), args.wasm.resolve(), preset, args.messaging)
