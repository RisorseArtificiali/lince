import runpy
import unittest
from pathlib import Path

configure = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'setup-clipboard.py'))['configure']


class ClipboardTests(unittest.TestCase):
    def config(self, text='', system='linux', wayland=False, display=False, commands=()):
        return configure(text, system=system, wayland=wayland, display=display,
                         which=lambda name: name if name in commands else None)

    def test_native_backend_and_idempotence(self):
        for system, wayland, display, executable, command in [
            ('linux', True, True, 'wl-copy', 'wl-copy'),
            ('linux', False, True, 'xclip', 'xclip -selection clipboard'),
            ('linux', False, True, 'xsel', 'xsel --clipboard --input'),
            ('darwin', False, False, 'pbcopy', 'pbcopy'),
        ]:
            args = dict(system=system, wayland=wayland, display=display, commands=[executable])
            text = self.config(**args)
            self.assertIn(f'copy_command "{command}"', text)
            self.assertIn('copy_on_select true', text)
            self.assertEqual(self.config(text, **args), text)

    def test_no_missing_backend_or_headless_command(self):
        self.assertNotIn('copy_command', self.config(wayland=True))
        self.assertNotIn('copy_command', self.config(commands=['xclip']))

    def test_custom_preferences_preserved(self):
        text = 'copy_command "custom-copy"\ncopy_on_select false\n'
        self.assertEqual(self.config(text, wayland=True, commands=['wl-copy']), text)

    def test_locked_copy_does_not_capture_ctrl_c(self):
        text = 'keybinds {\n    locked {\n        bind "Ctrl l" { SwitchToMode "normal"; }\n    }\n}\n'
        result = self.config(text)
        self.assertIn('bind "Ctrl Shift c" { Copy; }', result)
        self.assertNotIn('bind "Ctrl c"', result)
        self.assertEqual(self.config(result), result)
