"""Clipboard output backend using wl-copy (Wayland) or xclip (X11)."""

import os
import shutil
import subprocess


class ClipboardBridge:
    """Copy transcribed text to the system clipboard.

    Detects Wayland vs X11 from environment variables and uses the appropriate tool.
    """

    def __init__(self) -> None:
        wayland = os.environ.get("WAYLAND_DISPLAY")
        display = os.environ.get("DISPLAY")

        if wayland:
            self._backend = "wl-copy"
            if not shutil.which("wl-copy"):
                raise RuntimeError(
                    "wl-copy not found. Install with: sudo dnf install wl-clipboard  "
                    "(or: sudo apt install wl-clipboard)"
                )
        elif display:
            self._backend = "xclip"
            if not shutil.which("xclip"):
                raise RuntimeError(
                    "xclip not found. Install with: sudo dnf install xclip  "
                    "(or: sudo apt install xclip)"
                )
        else:
            raise RuntimeError(
                "No display server detected (WAYLAND_DISPLAY and DISPLAY are both unset). "
                "Clipboard output requires a running Wayland or X11 session."
            )

    def send_text(self, text: str) -> None:
        """Copy text to the system clipboard."""
        if self._backend == "wl-copy":
            subprocess.run(["wl-copy", "--", text], check=True)
        else:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode(),
                check=True,
            )
