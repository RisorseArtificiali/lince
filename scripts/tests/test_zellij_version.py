"""Check installer version gates without running installation side effects."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = (ROOT / 'scripts/check-zellij.sh').read_text()
BOOTSTRAP = (ROOT / 'docs/install').read_text()
BOOTSTRAP_CHECK = BOOTSTRAP[BOOTSTRAP.index('check_zellij_version() {'):].split('\nif ! check_zellij_version;', 1)[0]


class ZellijVersionTest(unittest.TestCase):
    def test_version_gate(self):
        cases = [
            (None, 0, False), ('zellij 0.44.0', 0, False),
            ('zellij 0.44.3', 0, False), ('zellij 0.45.0', 0, False),
            ('zellij 0.45.1', 0, True), ('zellij 0.45.10', 0, True),
            ('zellij 0.46.0', 0, True), ('zellij 1.0.0', 0, True),
            ('zellij 0.45.1-rc.1', 0, False), ('garbage', 0, False),
            ('', 0, False), ('zellij 0.45.1', 1, False),
        ]
        for check in (HELPER, BOOTSTRAP_CHECK):
            for version, status, accepted in cases:
                with self.subTest(version=version, status=status, bootstrap=check == BOOTSTRAP_CHECK):
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory)
                        (path / 'awk').symlink_to(shutil.which('awk'))
                        if version is not None:
                            stub = path / 'zellij'
                            stub.write_text('#!/bin/bash\nprintf "%s\\n" "$TEST_VERSION"\nexit "$TEST_STATUS"\n')
                            stub.chmod(0o755)
                        result = subprocess.run(
                            ['/bin/bash', '-c', check + '\ncheck_zellij_version'],
                            env={**os.environ, 'PATH': directory, 'TEST_VERSION': version or '', 'TEST_STATUS': str(status)},
                            capture_output=True, text=True,
                        )
                        self.assertEqual(result.returncode == 0, accepted, result.stderr)
                        if not accepted:
                            self.assertIn('Zellij >= 0.45.1 required', result.stderr)

    def test_bootstrap_matches_shared_check(self):
        self.assertEqual(HELPER[HELPER.index('check_zellij_version() {'):].strip(), BOOTSTRAP_CHECK.strip())


if __name__ == '__main__':
    unittest.main()
