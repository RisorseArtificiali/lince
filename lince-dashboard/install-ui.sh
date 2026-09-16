#!/usr/bin/env bash
# Shared by install.sh and update.sh: presentation assets have identical coverage.
set -euo pipefail
UI_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/zellij/layouts" "$HOME/.config/lince-dashboard" "$HOME/.local/bin"
for layout in "$UI_SOURCE"/layouts/*.kdl; do
    cp "$layout" "$HOME/.config/zellij/layouts/"
done
cp "$UI_SOURCE/lince-voice" "$HOME/.local/bin/lince-voice"
chmod +x "$HOME/.local/bin/lince-voice"
cp "$UI_SOURCE/lince-dashboard-launch" "$HOME/.local/bin/lince-dashboard-launch"
chmod +x "$HOME/.local/bin/lince-dashboard-launch"
# The active session config is user-owned; refreshed defaults remain reviewable.
if [ ! -f "$HOME/.config/lince-dashboard/zellij.kdl" ]; then
    cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl"
fi
cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl.dist"
# Upgrade only known LINCE aliases, leaving unrelated/custom commands intact.
python3 - "$HOME/.bashrc" "$HOME/.zshrc" <<'PY'
from pathlib import Path
import sys
replacements = {
    'alias lince="zellij --layout dashboard-tiled"': 'alias lince="lince-dashboard-launch"',
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
    'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }',
]) + '\n        bind "Ctrl l" { SwitchToMode "normal"; }\n    }'
updated = text.replace(old_locked, new_locked)
for old, new in replacements.items():
    updated = updated.replace(old, new)
# Add Alt+q alongside known LINCE wizard bindings in each mode. Preserve an
# existing custom Alt+q binding instead of silently replacing it.
if 'bind "Alt q"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt n" \{ MessagePlugin \{ name "lince-ui-open"; payload "wizard"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt q" { MessagePlugin { name "lince-save-quit"; }; }', updated)
if 'bind "Alt b"' not in updated:
    updated = re.sub(r'(?m)^([ \t]*)(bind "Alt s" \{ MessagePlugin \{ name "lince-sidebar-toggle"; \}; \})$',
        lambda m: m.group(0) + '\n' + m.group(1) + 'bind "Alt b" { MessagePlugin { name "lince-statusbar-toggle"; }; }', updated)
for key, binding in [
    ('Alt v', 'bind "Alt v" { MessagePlugin { name "lince-ui-open"; payload "voice"; }; }'),
    ('Alt m', 'bind "Alt m" { MessagePlugin { name "lince-voice-mute"; }; }'),
    ('Alt t', 'bind "Alt t" { MessagePlugin { name "lince-voice-ptt"; }; }'),
    ('Alt x', 'bind "Alt x" { MessagePlugin { name "kill-focused-agent"; }; }'),
    ('Alt ?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
    ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; }; }'),
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
        ('Alt ?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
        ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; }; }'),
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
        ('?', 'bind "Alt ?" { MessagePlugin { name "lince-ui-open"; payload "help"; }; }'),
        ('Ctrl Space', 'bind "Ctrl Space" { MessagePlugin { name "lince-voice-ptt"; }; }'),
    ]:
        binding_key = key if key == 'Ctrl Space' else f'Alt {key}'
        if f'bind "{binding_key}"' not in body:
            body += f'        {binding}\n'
    return body
updated = re.sub(r'(?m)^    locked \{\n(?:(?!^    \}).*\n)*', add_locked_shortcuts, updated)
if updated != text:
    path.with_suffix('.kdl.bak-shortcuts').write_text(text)
    path.write_text(updated)
PY

# Configure local clipboard transport on both installation and update.
python3 "$UI_SOURCE/setup-clipboard.py" "$HOME/.config/lince-dashboard/zellij.kdl"
