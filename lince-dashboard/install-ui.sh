#!/usr/bin/env bash
# Shared by install.sh and update.sh: presentation assets have identical coverage.
set -euo pipefail
UI_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/zellij/layouts" "$HOME/.config/lince-dashboard" "$HOME/.local/bin"
for layout in "$UI_SOURCE"/layouts/*.kdl; do
    cp "$layout" "$HOME/.config/zellij/layouts/"
done
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
if updated != text:
    path.with_suffix('.kdl.bak-shortcuts').write_text(text)
    path.write_text(updated)
PY
