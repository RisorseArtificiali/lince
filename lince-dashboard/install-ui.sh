#!/usr/bin/env bash
# Shared by install.sh and update.sh: presentation assets have identical coverage.
set -euo pipefail
UI_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$UI_SOURCE/../lince-messages/install.sh" --runtime-only
mkdir -p "$HOME/.config/zellij/layouts" "$HOME/.config/lince-dashboard" "$HOME/.local/bin"
for layout in "$UI_SOURCE"/layouts/*.kdl; do
    cp "$layout" "$HOME/.config/zellij/layouts/"
done
# Zellij passes layout plugin configuration synchronously. Match the display
# style to the host before the plugin's user config is loaded asynchronously.
python3 - "$HOME/.config/zellij/layouts"/*.kdl <<'PY'
from pathlib import Path
import platform
import sys

style = "ctrl" if platform.system() == "Darwin" else "alt"
for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    text = path.read_text()
    updated = text.replace('keybinding_style "alt"', f'keybinding_style "{style}"')
    if updated != text:
        path.write_text(updated)
PY
cp "$UI_SOURCE/lince-voice" "$HOME/.local/bin/lince-voice"
chmod +x "$HOME/.local/bin/lince-voice"
cp "$UI_SOURCE/lince-dashboard-launch" "$HOME/.local/bin/lince-dashboard-launch"
chmod +x "$HOME/.local/bin/lince-dashboard-launch"

# The curl bootstrap may provision Python outside the normal PATH. Keep the
# installed launcher bound to that managed interpreter without shadowing the
# user's generic `python3` command.
MANAGED_PYTHON="$HOME/.local/share/lince/python/bin/python3"
if [ -x "$MANAGED_PYTHON" ]; then
    PYTHON_SHIM="$HOME/.local/bin/lince-python"
    PYTHON_SHIM_NEW="${PYTHON_SHIM}.new.$$"
    cat > "$PYTHON_SHIM_NEW" <<'SHIM'
#!/bin/sh
# Managed by LINCE for the standalone bootstrap interpreter.
managed_python="$HOME/.local/share/lince/python/bin/python3"
if [ ! -x "$managed_python" ]; then
    echo "lince: managed Python is missing; re-run the LINCE installer" >&2
    exit 1
fi
export PATH="$HOME/.local/share/lince/python/bin:$PATH"
exec "$managed_python" "$@"
SHIM
    chmod 755 "$PYTHON_SHIM_NEW"
    mv "$PYTHON_SHIM_NEW" "$PYTHON_SHIM"

    LAUNCHER_NEW="$HOME/.local/bin/.lince-dashboard-launch.new.$$"
    {
        printf '%s\n' '#!/usr/bin/env lince-python'
        tail -n +2 "$UI_SOURCE/lince-dashboard-launch"
    } > "$LAUNCHER_NEW"
    chmod 755 "$LAUNCHER_NEW"
    mv "$LAUNCHER_NEW" "$HOME/.local/bin/lince-dashboard-launch"
fi
cp "$UI_SOURCE/lince" "$HOME/.local/bin/lince"
chmod +x "$HOME/.local/bin/lince"
# The active session config is user-owned; refreshed defaults remain reviewable.
if [ ! -f "$HOME/.config/lince-dashboard/zellij.kdl" ]; then
    cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl"
fi
cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl.dist"
# Tell the plugin which modifier to show in its help and attention hints.
# WASM cannot reliably identify the host OS, so choose once at install time;
# an explicit keybinding_style in the user's config is preserved.
python3 - "$HOME/.config/lince-dashboard/config.toml" <<'PY'
from pathlib import Path
import platform
import sys

path = Path(sys.argv[1])
style = "ctrl" if platform.system() == "Darwin" else "alt"
if path.exists():
    text = path.read_text()
else:
    text = "[dashboard]\n"
if "keybinding_style" not in text:
    marker = "[dashboard]\n"
    if marker in text:
        text = text.replace(marker, marker + f'keybinding_style = "{style}"\n', 1)
    else:
        text = marker + f'keybinding_style = "{style}"\n\n' + text
    path.write_text(text)
PY
# Upgrade only known LINCE aliases, leaving unrelated/custom commands intact.
python3 - "$HOME/.bashrc" "$HOME/.zshrc" <<'PY'
from pathlib import Path
import sys
replacements = {
    'alias lince="zellij --layout dashboard-tiled"': 'alias lince=\'"$HOME/.local/bin/lince"\'',
    'alias lince="lince-dashboard-launch"': 'alias lince=\'"$HOME/.local/bin/lince"\'',
    'alias lince="$HOME/.local/bin/lince"': 'alias lince=\'"$HOME/.local/bin/lince"\'',
    'alias lince-floating="zellij --layout dashboard"': 'alias lince-floating="lince-dashboard-launch --layout dashboard"',
    'alias zd="zellij --layout dashboard-tiled"': 'alias zd="lince-dashboard-launch"',
}
for filename in sys.argv[1:]:
    path = Path(filename)
    if not path.exists():
        continue
    text = path.read_text()
    if '# LINCE aliases' not in text:
        continue
    updated = '\n'.join(replacements.get(line, line) for line in text.split('\n'))
    if updated != text:
        path.write_text(updated)
PY
python3 - "$HOME/.config/lince-dashboard/zellij.kdl" <<'PY'
from pathlib import Path
import sys
import re
path = Path(sys.argv[1])
text = path.read_text()
replacements = {
    'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; }; }': 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; payload "submit"; }; }',
    'bind "Alt x" { MessagePlugin { name "lince-voice-ptt"; }; }': 'bind "Alt x" { MessagePlugin { name "kill-focused-agent"; }; }',
    'bind "Alt j" { MoveFocus "down"; }': 'bind "Alt j" { MessagePlugin { name "cycle-agent"; payload "next"; }; }',
    'bind "Alt k" { MoveFocus "up"; }': 'bind "Alt k" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }',
    'bind "Alt left" { MoveFocusOrTab "left"; }': 'bind "Alt left" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }',
    'bind "Alt right" { MoveFocusOrTab "right"; }': 'bind "Alt right" { MessagePlugin { name "cycle-agent"; payload "next"; }; }',
    'bind "Alt h" { MoveFocusOrTab "left"; }': 'bind "Alt h" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }',
    'bind "Alt i" { MoveTab "left"; }': 'bind "Alt i" { MessagePlugin { name "lince-ui-open"; payload "info"; }; }',
    'bind "Alt l" { MoveFocusOrTab "right"; }': 'bind "Alt s" { MessagePlugin { name "lince-sidebar-toggle"; }; }',
    'bind "Alt l" { MessagePlugin { name "lince-sidebar-toggle"; }; }': 'bind "Alt s" { MessagePlugin { name "lince-sidebar-toggle"; }; }',
    'bind "Alt n" { NewPane; }': 'bind "Alt n" { MessagePlugin { name "lince-ui-open"; payload "wizard"; }; }',
}
old_locked = '    locked {\n        bind "Ctrl l" { SwitchToMode "normal"; }\n    }'
new_locked = '    locked {\n' + '\n'.join('        ' + binding for binding in [
    'bind "Alt d" { MessagePlugin { name "lince-ui-open"; }; }',
    *dict.fromkeys(replacements.values()),
    'bind "Alt m" { MessagePlugin { name "lince-voice-mute"; }; }',
    'bind "Alt t" { MessagePlugin { name "lince-voice-ptt"; }; }',
    'bind "Alt r" { MessagePlugin { name "rename-focused-agent"; }; }',
    'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }',
]) + '\n        bind "Ctrl l" { SwitchToMode "normal"; }\n    }'
updated = text.replace(old_locked, new_locked)
for old, new in replacements.items():
    updated = updated.replace(old, new)
# Release only the old shipped vertical focus shortcuts. Custom actions stay
# user-owned; clear-defaults=true lets unbound keys reach the focused terminal.
updated = re.sub(r'(?m)^[ \t]*bind "Alt (up|down)" \{ MoveFocus "\1"; \}[ \t]*\n', '', updated)
# Add Alt+q alongside known LINCE wizard bindings in each mode. Preserve an
# existing custom Alt+q binding instead of silently replacing it.
if 'bind "Alt q"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt n" \{ MessagePlugin \{ name "lince-ui-open"; payload "wizard"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt q" { MessagePlugin { name "lince-save-quit"; }; }', updated)
if 'bind "Alt Shift q"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt q" \{ MessagePlugin \{ name "lince-save-quit"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt Shift q" { MessagePlugin { name "lince-quit"; }; }', updated)
if 'bind "Alt Shift n"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt n" \{ MessagePlugin \{ name "lince-ui-open"; payload "wizard"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt Shift n" { MessagePlugin { name "lince-ui-open"; payload "defaults"; }; }', updated)
if 'bind "Alt b"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt s" \{ MessagePlugin \{ name "lince-sidebar-toggle"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt b" { MessagePlugin { name "lince-statusbar-toggle"; }; }', updated)
for key, binding in [
    ('Alt v', 'bind "Alt v" { MessagePlugin { name "lince-ui-open"; payload "voice"; }; }'),
    ('Alt m', 'bind "Alt m" { MessagePlugin { name "lince-voice-mute"; }; }'),
    ('Alt t', 'bind "Alt t" { MessagePlugin { name "lince-voice-ptt"; }; }'),
    ('Alt x', 'bind "Alt x" { MessagePlugin { name "kill-focused-agent"; }; }'),
    ('Alt r', 'bind "Alt r" { MessagePlugin { name "rename-focused-agent"; }; }'),
    ('Alt ?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
    ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; payload "submit"; }; }'),
]:
    if f'bind "{key}"' not in updated:
        updated = re.sub(r'(?m)^([ \t]*)(bind "Alt n" \{ MessagePlugin \{ name "lince-ui-open"; payload "wizard"; \}; \})$',
            lambda m: m.group(0) + '\n' + m.group(1) + binding, updated)
# Add global LINCE shortcuts in existing normal/locked blocks without overriding custom bindings.
def add_shared_shortcuts(match):
    body = match.group(0)
    for key, binding in [
        ('Alt v', 'bind "Alt v" { MessagePlugin { name "lince-ui-open"; payload "voice"; }; }'),
        ('Alt m', 'bind "Alt m" { MessagePlugin { name "lince-voice-mute"; }; }'),
        ('Alt t', 'bind "Alt t" { MessagePlugin { name "lince-voice-ptt"; }; }'),
        ('Alt x', 'bind "Alt x" { MessagePlugin { name "kill-focused-agent"; }; }'),
        ('Alt r', 'bind "Alt r" { MessagePlugin { name "rename-focused-agent"; }; }'),
        ('Alt ?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
        ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; payload "submit"; }; }'),
    ]:
        if f'bind "{key}"' not in body:
            body += f'        {binding}\n'
    return body
updated = re.sub(r'(?m)^    shared_except "locked" \{\n(?:(?!^    \}).*\n)*', add_shared_shortcuts, updated)

def add_locked_shortcuts(match):
    body = match.group(0)
    for key, binding in [
        ('v', 'bind "Alt v" { MessagePlugin { name "lince-ui-open"; payload "voice"; }; }'),
        ('left', 'bind "Alt left" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }'),
        ('right', 'bind "Alt right" { MessagePlugin { name "cycle-agent"; payload "next"; }; }'),
        ('j', 'bind "Alt j" { MessagePlugin { name "cycle-agent"; payload "next"; }; }'),
        ('k', 'bind "Alt k" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }'),
        ('m', 'bind "Alt m" { MessagePlugin { name "lince-voice-mute"; }; }'),
        ('t', 'bind "Alt t" { MessagePlugin { name "lince-voice-ptt"; }; }'),
        ('x', 'bind "Alt x" { MessagePlugin { name "kill-focused-agent"; }; }'),
        ('r', 'bind "Alt r" { MessagePlugin { name "rename-focused-agent"; }; }'),
        ('?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
        ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; payload "submit"; }; }'),
    ]:
        binding_key = key if key == 'Ctrl Space' else f'Alt {key}'
        if f'bind "{binding_key}"' not in body:
            body += f'        {binding}\n'
    return body
updated = re.sub(r'(?m)^    locked \{\n(?:(?!^    \}).*\n)*', add_locked_shortcuts, updated)

# macOS commonly maps Option to character input rather than an Alt modifier.
# Add Control aliases in both global modes, but leave an existing custom
# Control binding untouched.
# Replace the shipped Zellij Ctrl+q quit binding with Lince's save-and-quit
# action before adding aliases. A user-defined action with another command is
# left untouched by the presence check below.
updated = updated.replace(
    'bind "Ctrl q" { Quit; }',
    'bind "Ctrl q" { MessagePlugin { name "lince-save-quit"; }; }',
)
updated = updated.replace(
    'bind "Ctrl h" { SwitchToMode "move"; }',
    'bind "Ctrl Shift u" { SwitchToMode "move"; }',
)

control_bindings = [
    ('Ctrl j', 'bind "Ctrl j" { MessagePlugin { name "cycle-agent"; payload "next"; }; }'),
    ('Ctrl k', 'bind "Ctrl k" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }'),
    ('Ctrl left', 'bind "Ctrl left" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }'),
    ('Ctrl right', 'bind "Ctrl right" { MessagePlugin { name "cycle-agent"; payload "next"; }; }'),
    ('Ctrl PageUp', 'bind "Ctrl PageUp" { MessagePlugin { name "cycle-agent"; payload "prev"; }; }'),
    ('Ctrl PageDown', 'bind "Ctrl PageDown" { MessagePlugin { name "cycle-agent"; payload "next"; }; }'),
    *[(f'Ctrl {n}', f'bind "Ctrl {n}" {{ MessagePlugin {{ name "focus-agent"; payload "{n}"; }}; }}')
      for n in range(1, 10)],
    ('Ctrl d', 'bind "Ctrl d" { MessagePlugin { name "lince-ui-open"; }; }'),
    ('Ctrl i', 'bind "Ctrl i" { MessagePlugin { name "lince-ui-open"; payload "info"; }; }'),
    ('Ctrl v', 'bind "Ctrl v" { MessagePlugin { name "lince-ui-open"; payload "voice"; }; }'),
    ('Ctrl m', 'bind "Ctrl m" { MessagePlugin { name "lince-voice-mute"; }; }'),
    ('Ctrl t', 'bind "Ctrl t" { MessagePlugin { name "lince-voice-ptt"; }; }'),
    ('Ctrl x', 'bind "Ctrl x" { MessagePlugin { name "kill-focused-agent"; }; }'),
    ('Ctrl r', 'bind "Ctrl r" { MessagePlugin { name "rename-focused-agent"; }; }'),
    ('Ctrl h', 'bind "Ctrl h" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
    ('Ctrl s', 'bind "Ctrl s" { MessagePlugin { name "lince-sidebar-toggle"; }; }'),
    ('Ctrl b', 'bind "Ctrl b" { MessagePlugin { name "lince-statusbar-toggle"; }; }'),
    ('Ctrl n', 'bind "Ctrl n" { MessagePlugin { name "lince-ui-open"; payload "wizard"; }; }'),
    ('Ctrl Shift n', 'bind "Ctrl Shift n" { MessagePlugin { name "lince-ui-open"; payload "defaults"; }; }'),
    ('Ctrl q', 'bind "Ctrl q" { MessagePlugin { name "lince-save-quit"; }; }'),
    ('Ctrl Shift q', 'bind "Ctrl Shift q" { MessagePlugin { name "lince-quit"; }; }'),
]

def add_control_aliases(match):
    body = match.group(0)
    for key, binding in control_bindings:
        if key in ('Ctrl h', 'Ctrl m', 'Ctrl t', 'Ctrl s', 'Ctrl b', 'Ctrl n') \
                and f'bind "Ctrl Shift {key[5:]}"' in body:
            continue
        if f'bind "{key}"' not in body:
            body += f'        {binding}\n'
    return body

updated = re.sub(r'(?m)^    locked \{\n(?:(?!^    \}).*\n)*', add_control_aliases, updated)
updated = re.sub(r'(?m)^    shared_except "locked" \{\n(?:(?!^    \}).*\n)*', add_control_aliases, updated)

# Normal mode reserves Ctrl+h/m/t/s/b/n for Zellij's mode navigation. Keep
# those aliases usable by adding Shift in normal mode; locked mode retains the
# shorter Ctrl variants above.
def shift_normal_conflicts(match):
    body = match.group(0)
    body = body.replace(
        'bind "Ctrl Shift n" { MessagePlugin { name "lince-ui-open"; payload "defaults"; }; }',
        'bind "Ctrl Shift d" { MessagePlugin { name "lince-ui-open"; payload "defaults"; }; }',
    )
    for key in ('m', 't', 's', 'b', 'n'):
        body = body.replace(
            f'bind "Ctrl {key}" {{ MessagePlugin',
            f'bind "Ctrl Shift {key}" {{ MessagePlugin',
        )
    return body

updated = re.sub(r'(?m)^    shared_except "locked" \{\n(?:(?!^    \}).*\n)*',
                 shift_normal_conflicts, updated)
if updated != text:
    path.with_suffix('.kdl.bak-shortcuts').write_text(text)
    path.write_text(updated)
PY

# Configure local clipboard transport on both installation and update.
python3 "$UI_SOURCE/setup-clipboard.py" "$HOME/.config/lince-dashboard/zellij.kdl"
