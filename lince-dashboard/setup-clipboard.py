#!/usr/bin/env python3
"""Configure native clipboard transport without replacing user preferences."""
import os
from pathlib import Path
import re
import shutil
import sys


def configure(text, *, system, wayland, display, which=shutil.which):
    if not re.search(r'^\s*copy_command\s+"', text, re.M):
        candidates = ([('pbcopy', 'pbcopy')] if system == 'darwin' else
                      [('wl-copy', 'wl-copy')] if wayland else
                      [('xclip', 'xclip -selection clipboard'), ('xsel', 'xsel --clipboard --input')]
                      if display else [])
        for executable, command in candidates:
            if which(executable):
                text += f'\n// Native clipboard backend configured by LINCE.\ncopy_command "{command}"\n'
                break
    if not re.search(r'^\s*copy_on_select\s+', text, re.M):
        text += '\ncopy_on_select true\n'
    # Extend the shipped locked block only; preserve any custom binding.
    locked = re.search(r'(?m)^    locked \{\n(.*?)^    \}', text, re.S)
    if locked and '"Ctrl Shift c"' not in locked.group(1):
        start = locked.start(1)
        text = text[:start] + '        bind "Ctrl Shift c" { Copy; }\n' + text[start:]
    return text


def main():
    path = Path(sys.argv[1])
    original = path.read_text()
    updated = configure(original, system=sys.platform,
                        wayland=bool(os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland'),
                        display=bool(os.environ.get('DISPLAY')))
    if updated != original:
        path.with_suffix('.kdl.bak-clipboard').write_text(original)
        path.write_text(updated)
    if not re.search(r'^\s*copy_command\s+"', updated, re.M):
        print('Clipboard: using terminal OSC 52; install wl-clipboard (Wayland) or xclip (X11) for native copy.')


if __name__ == '__main__':
    main()
