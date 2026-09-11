#!/usr/bin/env python3
"""Export actual Rust renderer output as terminal SVG captures (requires rich).

Run: tests/run-plugin-tests.sh --ignored --nocapture theme_previews > /tmp/lince-previews.txt
     python3 tests/render-theme-previews.py /tmp/lince-previews.txt
"""
import io
import re
import sys
from pathlib import Path
from rich.console import Console
from rich.text import Text

root = Path(__file__).resolve().parents[2]
for name, output in re.findall(r"PREVIEW:([^\n]+)\n(.*?)\nENDPREVIEW", Path(sys.argv[1]).read_text(), re.S):
    console = Console(record=True, width=76, file=io.StringIO(), force_terminal=True)
    console.print(Text.from_ansi(output), end="")
    console.save_svg(str(root / "docs/assets" / f"dashboard-theme-{name}.svg"), title=f"LINCE — {name}")
