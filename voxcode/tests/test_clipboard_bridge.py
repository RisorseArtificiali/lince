"""Tests for ClipboardBridge."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from voxcode.clipboard_bridge import ClipboardBridge


class TestClipboardBridgeInit:
    def test_wayland_detection(self):
        with (
            patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=False),
            patch("shutil.which", return_value="/usr/bin/wl-copy"),
        ):
            bridge = ClipboardBridge()
            assert bridge._backend == "wl-copy"

    def test_x11_detection_no_wayland(self):
        env = {"DISPLAY": ":0"}
        # Ensure WAYLAND_DISPLAY is absent
        with (
            patch.dict("os.environ", env, clear=True),
            patch("shutil.which", return_value="/usr/bin/xclip"),
        ):
            bridge = ClipboardBridge()
            assert bridge._backend == "xclip"

    def test_wayland_takes_priority_over_x11(self):
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch("shutil.which", return_value="/usr/bin/wl-copy"),
        ):
            bridge = ClipboardBridge()
            assert bridge._backend == "wl-copy"

    def test_no_display_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="No display server detected"):
                ClipboardBridge()

    def test_wl_copy_missing_raises(self):
        with (
            patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True),
            patch("shutil.which", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="wl-copy not found"):
                ClipboardBridge()

    def test_xclip_missing_raises(self):
        with (
            patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True),
            patch("shutil.which", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="xclip not found"):
                ClipboardBridge()


class TestClipboardBridgeSendText:
    def _make_bridge(self, backend: str) -> ClipboardBridge:
        bridge = ClipboardBridge.__new__(ClipboardBridge)
        bridge._backend = backend
        return bridge

    def test_wl_copy_command(self):
        bridge = self._make_bridge("wl-copy")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("hello world")
            mock_run.assert_called_once_with(["wl-copy", "--", "hello world"], check=True)

    def test_wl_copy_text_starting_with_dash(self):
        bridge = self._make_bridge("wl-copy")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("-dangerous flag")
            mock_run.assert_called_once_with(["wl-copy", "--", "-dangerous flag"], check=True)

    def test_xclip_command(self):
        bridge = self._make_bridge("xclip")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("hello world")
            mock_run.assert_called_once_with(
                ["xclip", "-selection", "clipboard"],
                input=b"hello world",
                check=True,
            )

    def test_no_trailing_newline_added_wl_copy(self):
        bridge = self._make_bridge("wl-copy")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("text without newline")
            args = mock_run.call_args[0][0]
            assert args[-1] == "text without newline"

    def test_no_trailing_newline_added_xclip(self):
        bridge = self._make_bridge("xclip")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("text without newline")
            assert mock_run.call_args[1]["input"] == b"text without newline"

    def test_existing_newline_preserved_xclip(self):
        bridge = self._make_bridge("xclip")
        with patch("subprocess.run") as mock_run:
            bridge.send_text("line\n")
            assert mock_run.call_args[1]["input"] == b"line\n"
