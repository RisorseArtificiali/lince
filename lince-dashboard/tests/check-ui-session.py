#!/usr/bin/env python3
"""Exercise real Zellij plugin roles with harmless fixture agents and no user state.

Requires Zellij >= 0.45.1 and a built WASM. Uses disposable sessions/config/cache.
  python3 tests/check-ui-session.py --zellij /path/to/zellij
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
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


def check(zellij, wasm, preset):
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
        # Resolve only a harmless sleep process: never launch a real AI CLI.
        fixture = {"agents": {"fixture": {"display_name": "Fixture", "short_label": "FIX",
            "color": "green", "command": ["/bin/sleep", "600"],
            "dashboard": {"pane_title_pattern": "sleep", "has_native_hooks": True}}}}
        (work / "lince-config").write_text("#!/bin/sh\ncat <<'FIXTURE'\n" + json.dumps(fixture) + "\nFIXTURE\n")
        (work / "lince-config").chmod(0o755)
        (work / ".lince-dashboard").write_text(json.dumps({"version": 3, "next_agent_id": 0,
            "agents": [{"name": f"fixture{i}", "agent_type": "fixture", "project_dir": str(work)}
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
        env = {key: value for key, value in os.environ.items() if not key.startswith("ZELLIJ")}
        env.update(TERM="xterm-256color", XDG_CACHE_HOME=str(work / "cache"),
                   PATH=f"{Path(zellij).parent}:{work}:{os.environ['PATH']}")
        session = f"lince-ui-test-{uuid.uuid4().hex[:10]}"
        process = subprocess.Popen(
            [zellij, "--config", str(work / "session.kdl"), "--config-dir", str(work),
             "--data-dir", str(work / "data"), "--layout", str(work / "layout.kdl"),
             "options", "--session-name", session], cwd=work, env=env,
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        output = bytearray()

        def pump():
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(master, 100000))
                except OSError:
                    pass

        def cli(arguments):
            command = subprocess.Popen([zellij, *arguments], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, env=env)
            deadline = time.monotonic() + 10
            while True:
                pump()
                try:
                    stdout, stderr = command.communicate(timeout=0.1)
                    return command.returncode, stdout, stderr
                except subprocess.TimeoutExpired:
                    if time.monotonic() > deadline:
                        command.kill()
                        command.communicate()
                        raise AssertionError(f"Zellij command timed out: {arguments}")

        def panes():
            status, stdout, _ = cli(["-s", session, "action", "list-panes", "--json"])
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

        def wait_for(predicate):
            end = time.monotonic() + 15
            while time.monotonic() < end:
                pump()
                current = {pane["title"]: pane for pane in panes()}
                if predicate(current):
                    return current
                if process.poll() is not None:
                    break
            fields = ("title", "is_suppressed", "is_focused", "pane_x", "pane_y", "pane_columns", "pane_rows", "terminal_command")
            summary = [{k: p[k] for k in fields} for p in panes()]
            raise AssertionError(f"{preset}: UI condition timed out; panes={summary}")

        def visible(name, expected):
            return lambda ps: (name in ps and (not ps[name]["is_suppressed"]) == expected
                and (name != "lince-dialog" or not expected or ps[name]["is_focused"]))

        def key(data):
            os.write(master, data)

        try:
            initial = wait_for(lambda ps: visible("lince-dialog", False)(ps)
                and visible("lince-controller", preset == "minimal")(ps)
                and "lince-viewport" in ps and sum("fixture" in name and ps[name]["is_suppressed"]
                    for name in ps) == 3)
            assert initial["lince-attention"]["pane_rows"] == 2
            assert initial["lince-attention"]["pane_y"] == 30
            identities = {(p["id"], p["is_plugin"]) for p in panes()}
            assert len(identities) == 8
            viewport = initial["lince-viewport"]
            if preset == "statusline":
                assert viewport["pane_columns"] == 100, viewport
            # Global list/info/help/wizard all open one bordered passive popup.
            for shortcut in (b"\x1bd", b"\x1bi", b"\x1bh", b"\x1bn"):
                key(shortcut)
                shown = wait_for(visible("lince-dialog", True))
                assert shown["lince-viewport"]["pane_columns"] == viewport["pane_columns"]
                assert not shown["lince-attention"]["is_suppressed"]
                assert shown["lince-dialog"]["pane_y"] + shown["lince-dialog"]["pane_rows"] <= 30
                key(b"\x1b")
                wait_for(visible("lince-dialog", False))
            # Shortcuts are available in locked mode too.
            key(b"\x0c")
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
                status, stdout, _ = cli(["-s", session, "action", "list-tabs", "--json"])
                return status == 0 and any(tab["are_floating_panes_visible"] for tab in json.loads(stdout))

            key(b"\x1b1")
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
                assert visible("lince-sidebar-aux", expected)(changed)
                if expected:
                    assert changed["lince-controller"]["pane_x"] == 0, changed
                    assert changed["lince-controller"]["pane_y"] == 0, changed
                    assert changed["lince-controller"]["pane_rows"] == 21, changed
                    assert changed["lince-sidebar-aux"]["pane_x"] == 0, changed
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
            for shortcut in (b"\x1bb", b"\x1bs", b"\x1bb", b"\x1bs", b"\x1bb") * 2:
                if shortcut == b"\x1bb":
                    bar_mode = (bar_mode + 1) % 3
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
            for shown in (False, True, True):
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
                key(b"\x1bb")  # full -> hidden
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
                for expected_sidebar, expected_mode in ((True, "summary"), (False, "hidden")):
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
                        for _ in range(5): pump()
                        key(b"\x1bb")  # full -> hidden
                        wait_for(visible("lince-attention", False))
                        wait_for(agent_fills_viewport)
                    key(b"\x1bq")
                    deadline = time.monotonic() + 15
                    while process.poll() is None and time.monotonic() < deadline: pump()
                    assert process.poll() is not None
                    assert json.loads(state_path.read_text())["view"] == {
                        "sidebar_visible": False, "statusbar_mode": "hidden"}
            else:
                assert state_path.read_text() == original, "Quit without save modified previous state"
            print(f"{preset}: global popups, sidebar/status-bar combinations, agent geometry and {'save/quit' if preset == 'statusline' else 'quit without save'} OK")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zellij", default=shutil.which("zellij"))
    parser.add_argument("--wasm", type=Path,
                        default=ROOT / "plugin/target/wasm32-wasip1/release/lince-dashboard.wasm")
    args = parser.parse_args()
    if not args.zellij or not args.wasm.exists():
        parser.error("Zellij and a built WASM are required")
    for preset in ("statusline", "minimal"):
        check(str(Path(args.zellij).resolve()), args.wasm.resolve(), preset)
