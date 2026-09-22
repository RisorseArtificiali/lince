import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import uuid
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Packaging(unittest.TestCase):
    def test_optional_install_update_migration_disable_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {k: v for k, v in os.environ.items() if k != 'CODEX_HOME'}
            env.update(HOME=directory, XDG_CONFIG_HOME=str(home/'.config'), PI_CODING_AGENT_DIR=str(home/'.pi/agent'), LINCE_MESSAGES_INSTALL_DIR=str(home / 'lib'),
                       LINCE_MESSAGES_BIN_DIR=str(home / 'bin'))
            settings = home / '.claude/settings.json'
            settings.parent.mkdir()
            other = {'type': 'command', 'command': 'user-hook'}
            settings.write_text(json.dumps({'other': 42, 'hooks': {'Stop': [{'hooks': [other,
                {'type': 'command', 'command': 'lince-msg-hook claude'}]}]}}))
            def run(script, *args, check=True):
                return subprocess.run(['bash', str(ROOT / script), *args], env=env, capture_output=True,
                                      text=True, timeout=15, check=check)
            run('install.sh', '--runtime-only')
            self.assertFalse((home / '.config/lince-dashboard/communication.json').exists())
            self.assertEqual(json.loads(settings.read_text()), {'other': 42, 'hooks': {'Stop': [{'hooks': [other]}]}})
            run('install.sh', '--enable', 'claude', 'codex', 'bob', 'pi', 'opencode', 'amp', 'gemini', 'goose')
            for agent in ('claude', 'codex', 'bob'):
                self.assertTrue((home / f'.{agent}/skills/lince-converse/SKILL.md').exists())
            for directory in ('.pi/agent', '.config/opencode', '.config/amp', '.gemini', '.config/goose'):
                self.assertTrue((home / directory / 'skills/lince-converse/SKILL.md').exists())
            run('update.sh', '--runtime-only')
            self.assertNotIn('lince-msg-hook', settings.read_text())
            run('install.sh', '--disable', 'bob')
            self.assertFalse((home / '.bob/skills/lince-converse/SKILL.md').exists())
            edited = home / '.codex/skills/lince-converse/SKILL.md'
            edited.write_text('user-modified')
            run('uninstall.sh')
            run('uninstall.sh')
            self.assertEqual(edited.read_text(), 'user-modified')
            self.assertFalse((home / '.claude/skills/lince-converse/SKILL.md').exists())
            self.assertFalse((home / 'bin/lince-msg').exists())
            for directory in ('.pi/agent', '.config/opencode', '.config/amp', '.gemini', '.config/goose'):
                self.assertFalse((home / directory / 'skills/lince-converse/SKILL.md').exists())

    def test_wrapper_opt_in_identity_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {k: v for k, v in os.environ.items() if k != 'CODEX_HOME' and not k.startswith('LINCE_MSG_')}
            env.update(HOME=directory, ZELLIJ_SESSION_NAME='converse-package-' + uuid.uuid4().hex,
                       LINCE_MESSAGES_INSTALL_DIR=str(home/'lib'), LINCE_MESSAGES_BIN_DIR=str(home/'bin'))
            def run(*command):
                return subprocess.run(command, env=env, capture_output=True, text=True, timeout=15, check=True)
            run('bash', str(ROOT/'install.sh'), '--runtime-only')
            wrapper = str(home/'bin/lince-msg-host')
            probe = [sys.executable, '-c', "import os; print(bool(os.environ.get('LINCE_MSG_CREDENTIAL')))" ]
            try:
                self.assertEqual(run(wrapper, 'run', '--alias', 'A', '--agent', 'claude', '--', *probe).stdout.strip(), 'False')
                run('bash', str(ROOT/'install.sh'), '--enable', 'claude')
                self.assertEqual(run(wrapper, 'run', '--alias', 'A', '--agent', 'claude', '--', *probe).stdout.strip(), 'True')
                snapshot = json.loads(run(wrapper, 'request', 'snapshot', '--json', '{}').stdout)
                self.assertEqual(snapshot['instances'][0]['live'], 0)
                self.assertEqual(list((home/'.local/state/lince-messages/credentials').glob('*.token')), [])
            finally:
                run('bash', str(ROOT/'uninstall.sh'))

    def test_unowned_skill_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            skill = home / '.claude/skills/lince-converse/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('mine')
            env = {**os.environ, 'HOME': directory, 'LINCE_MESSAGES_INSTALL_DIR': str(home/'lib'),
                   'LINCE_MESSAGES_BIN_DIR': str(home/'bin')}
            result = subprocess.run(['bash', str(ROOT/'install.sh'), '--enable', 'claude'], env=env,
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(skill.read_text(), 'mine')


if __name__ == '__main__': unittest.main()
