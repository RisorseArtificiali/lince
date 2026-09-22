#!/usr/bin/env python3
"""macOS only: press the dashboard's Option shortcuts as real key events.

Opens a disposable dashboard session (fixture agents, fixture voice adapter) in a
real terminal application and sends Option+v / Option+m / Option+t / Option+h /
Esc through System Events, so the terminal's own Option-as-Meta translation is
exercised instead of the pre-encoded sequences used by check-ui-session.py.
Takes keyboard focus for about a minute. Requires a built plugin and the
Accessibility permission for the terminal running this script.
  python3 tests/macos-option-key-check.py            # Terminal.app
  python3 tests/macos-option-key-check.py iTerm      # any app name `open -a` accepts
"""
import json, os, runpy, shutil, subprocess, sys, tempfile, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = runpy.run_path(str(ROOT / "lince-dashboard-launch"))
zellij = shutil.which("zellij")
wasm = ROOT / "plugin/target/wasm32-wasip1/release/lince-dashboard.wasm"
work = Path(tempfile.mkdtemp(prefix="lince-optmeta-"))
app = sys.argv[1] if len(sys.argv) > 1 else "Terminal"

text = LAUNCHER["presentation_layout"](LAUNCHER["sidebar_layout"]((ROOT / "layouts/dashboard-statusline.kdl").read_text(), 15), "statusline", True, True)
text = text.replace("file:~/.config/zellij/plugins/lince-dashboard.wasm", f"file:{wasm}")
text = text.replace("~/.config/lince-dashboard/config.toml", str(work / "config.toml"))
text = text.replace('command "lince-viewport-placeholder"', 'command "sh"')
text += '\ndefault_shell "/bin/sh"\npane_frames false\nauto_layout false\nshow_startup_tips false\nshow_release_notes false\n'
(work / "layout.kdl").write_text(text)
(work / "config.toml").write_text('[dashboard]\nagent_layout="tiled"\ncompact=true\nsandbox_command="/bin/false"\n')
fixture = {"agents": {"fixture": {"display_name": "Fixture", "short_label": "FIX", "color": "green",
           "command": ["/bin/sleep", "600"], "dashboard": {"pane_title_pattern": "sleep", "has_native_hooks": True}}}}
(work / "lince-config").write_text("#!/bin/sh\ncat <<'FIXTURE'\n" + json.dumps(fixture) + "\nFIXTURE\n"); (work / "lince-config").chmod(0o755)
shutil.copyfile(ROOT / "tests/voice-fixture.py", work / "lince-voice"); (work / "lince-voice").chmod(0o755)
(work / "lince-msg-host").write_text('#!/bin/sh\nwhile [ "$1" != "--" ]; do shift; done\nshift\nexec "$@"\n'); (work / "lince-msg-host").chmod(0o755)
(work / ".lince-dashboard").write_text(json.dumps({"version": 3, "next_agent_id": 0, "agents": [
    {"name": f"fixture{i}", "agent_type": "fixture", "project_dir": str(work)} for i in (1, 2, 3)]}))
(work / "session.kdl").write_text((ROOT / "zellij-config/config.kdl").read_text()
    + f'\nenv {{ PATH "{work}:{Path(zellij).parent}:/usr/bin:/bin"; }}\n')
permissions = work / "Library/Caches/org.Zellij-Contributors.Zellij/permissions.kdl"
permissions.parent.mkdir(parents=True)
permissions.write_text(f'"{wasm}" {{\n RunCommands\n ReadApplicationState\n ReadCliPipes\n WriteToStdin\n'
                       ' ChangeApplicationState\n OpenTerminalsOrPlugins\n MessageAndLaunchOtherPlugins\n}\n')
session = f"lince-optmeta-{uuid.uuid4().hex[:8]}"
env = {k: v for k, v in os.environ.items() if not k.startswith("ZELLIJ")}
env.update(TERM="xterm-256color", HOME=str(work), PATH=f"{Path(zellij).parent}:{work}:{os.environ['PATH']}")
launcher = work / "run.command"
launcher.write_text(f'#!/bin/sh\ncd "{work}"\nexport HOME="{work}" TERM=xterm-256color PATH="{Path(zellij).parent}:{work}:/usr/bin:/bin"\n'
                    f'exec "{zellij}" --config "{work}/session.kdl" --config-dir "{work}" --data-dir "{work}/data" '
                    f'--layout "{work}/layout.kdl" options --session-name {session}\n')
launcher.chmod(0o755)

def cli(*args):
    r = subprocess.run([zellij, "-s", session, "action", *args], env=env, capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout
def panes():
    st, out = cli("list-panes", "--json", "--all")
    if st or not out.strip(): return {}
    try: return {p["title"]: p for p in json.loads(out)}
    except json.JSONDecodeError: return {}
def wait_for(cond, what, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ps = panes()
            if cond(ps): return ps
        except Exception: pass
        time.sleep(0.25)
    raise AssertionError(f"timeout: {what}; panes={[(t, p['is_suppressed']) for t, p in panes().items()]}")
visible = lambda title, yes: (lambda ps: title in ps and ps[title]["is_suppressed"] == (not yes))
def voice(expected):
    f = work / "lince-voice.json"
    return lambda ps: f.exists() and json.loads(f.read_text())["status"] == expected
def osa(script): subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
def key(k, opt=False):
    osa(f'tell application "{app}" to activate')
    osa(f'tell application "System Events" to keystroke "{k}"' + (' using {option down}' if opt else ''))
def esc():
    osa(f'tell application "{app}" to activate')
    osa(f'tell application "System Events" to key code 53')
def esc_close():
    esc()
    try:
        wait_for(visible("lince-dialog", False), "dialog hidden", 5)
    except AssertionError:
        d = panes().get("lince-dialog", {})
        results.append(("diag: dialog after first Esc", f"suppressed={d.get('is_suppressed')} focused={d.get('is_focused')}"))
        esc()
        wait_for(visible("lince-dialog", False), "dialog hidden after second Esc", 5)

results = []
def step(name, fn):
    try: fn(); results.append((name, "PASS"))
    except Exception as e: results.append((name, f"FAIL: {str(e)[:200]}"))
try:
    subprocess.run(["open", "-a", app, str(launcher)], check=True)
    wait_for(lambda ps: sum("fixture" in t for t in ps) == 3 and "lince-viewport" in ps, "session up", 40)
    time.sleep(1.5)
    # Focus the shell first so the popup has a target (same as the harness).
    cli("hide-floating-panes")
    step("Option+v opens the voice popup", lambda: (key("v", opt=True), wait_for(visible("lince-dialog", True), "dialog visible")))
    step("s saves settings", lambda: (key("s"), wait_for(lambda ps: (work/"lince-voice.json").exists() and json.loads((work/"lince-voice.json").read_text())["settings"]["configured"], "configured")))
    step("a starts listening", lambda: (key("a"), wait_for(voice("listening"), "listening")))
    step("Esc closes the popup", esc_close)
    step("Option+m mutes", lambda: (key("m", opt=True), wait_for(voice("muted"), "muted")))
    step("Option+m unmutes", lambda: (key("m", opt=True), wait_for(voice("listening"), "listening again")))
    step("Option+t starts PTT", lambda: (key("t", opt=True), wait_for(voice("recording"), "recording")))
    step("Option+t stops PTT", lambda: (key("t", opt=True), wait_for(voice("listening"), "listening after ptt")))
    step("Option+v then x stops", lambda: (key("v", opt=True), wait_for(visible("lince-dialog", True), "dialog"), key("x"), wait_for(voice("stopped"), "stopped"), esc_close()))
    step("Option+h opens help", lambda: (key("h", opt=True), wait_for(visible("lince-dialog", True), "help dialog"), esc_close()))
finally:
    subprocess.run([zellij, "kill-session", session], env=env, capture_output=True)
    time.sleep(1)
    try: osa(f'tell application "{app}" to close (every window whose name contains "run.command")')
    except Exception: pass
    try: osa(f'tell application "{app}" to close (every window whose name contains "{session}")')
    except Exception: pass
    print(json.dumps({"app": app, "work": str(work), "results": results}, indent=1))
    shutil.rmtree(work, ignore_errors=True)
