"""Replay captured original-TUI events; live observations are recorded separately."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import capabilities, invoke
from test_service import MailboxFixture


class NativeTuiEvidenceTests(MailboxFixture):
    def replay(self, agent, version):
        fixture = json.loads((Path(__file__).parent / f'fixtures/{agent}-{version}-tui-intervention.json').read_text())
        self.store.db.execute('UPDATE instances SET capabilities=? WHERE id=?',
                              (json.dumps(capabilities(agent, version)), self.b['instance']))
        credential = self.path / 'credential'
        credential.write_text(self.b['token'])
        request = self.rpc(self.a, 'delegate', recipient=self.b['instance'], group=self.group,
                           text='Owned work before human intervention', key='owned')['id']
        self.rpc(self.b, 'accept', request=request)
        self.host('automatic', instance=self.b['instance'], enabled=True)
        events = fixture['events']
        self.assertEqual([e['hook_event_name'] for e in events[:3]], ['SessionStart', 'UserPromptSubmit', 'Stop'])
        for payload in events[:3]:
            invoke(agent, payload, self.path / 'socket', credential)
        self.assertEqual(self.rpc(self.b, 'get', request=request)['work'], 'paused')
        instance = next(i for i in self.host('snapshot')['instances'] if i['id'] == self.b['instance'])
        self.assertEqual(instance['provenance'], 'human')
        # Release ownership so the permission test cannot pass merely because
        # the one-owned-item gate also suppresses delivery.
        self.rpc(self.b, 'resume', request=request)
        self.rpc(self.b, 'complete', request=request, text='Fixture finished', key='done')
        queued = self.send(key='permission-queue')['id']
        for payload in events[3:]:
            self.assertIsNone(invoke(agent, payload, self.path / 'socket', credential))
        self.assertEqual(events[-1]['hook_event_name'], 'PermissionRequest')
        instance = next(i for i in self.host('snapshot')['instances'] if i['id'] == self.b['instance'])
        self.assertEqual(instance['readiness'], 'permission')
        self.assertIsNone(instance['current'])
        self.assertEqual(self.rpc(self.b, 'get', request=queued)['delivery'], 'queued')

    def test_claude_original_tui_payloads(self):
        self.replay('claude', '2.1.272')

    def test_codex_original_tui_payloads(self):
        self.replay('codex', '0.154.0')

    def test_bob_original_tui_human_and_permission_payloads(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/bob-2.0.4-tui-intervention.json').read_text())
        self.store.db.execute('UPDATE instances SET capabilities=? WHERE id=?',
                              (json.dumps(capabilities('bob', '2.0.4')), self.b['instance']))
        credential = self.path / 'credential'
        credential.write_text(self.b['token'])
        events = fixture['events']
        initial_stop = next(i for i, event in enumerate(events) if event['hook_event_name'] == 'Stop')
        for payload in events[:initial_stop + 1]:
            invoke('bob', payload, self.path / 'socket', credential)
        request = self.rpc(self.a, 'delegate', recipient=self.b['instance'], group=self.group,
                           text='Owned before human input', key='owned')['id']
        self.rpc(self.b, 'accept', request=request)
        next_stop = next(i for i in range(initial_stop + 1, len(events)) if events[i]['hook_event_name'] == 'Stop')
        for payload in events[initial_stop + 1:next_stop + 1]:
            invoke('bob', payload, self.path / 'socket', credential)
        self.assertEqual(self.rpc(self.b, 'get', request=request)['work'], 'paused')
        instance = next(i for i in self.host('snapshot')['instances'] if i['id'] == self.b['instance'])
        self.assertEqual(instance['provenance'], 'human')
        self.rpc(self.b, 'resume', request=request)
        self.rpc(self.b, 'complete', request=request, text='Fixture releases ownership', key='done')
        queued = self.send(key='permission-queue')['id']
        for payload in events[next_stop + 1:]:
            self.assertIsNone(invoke('bob', payload, self.path / 'socket', credential))
        self.assertIn('PreToolUse', [e['hook_event_name'] for e in events[next_stop + 1:]])
        self.assertNotIn('PermissionRequest', [e['hook_event_name'] for e in events])
        self.error('unsupported', self.host, 'automatic', instance=self.b['instance'], enabled=True)
        self.assertEqual(self.rpc(self.b, 'get', request=queued)['delivery'], 'queued')
