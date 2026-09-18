#!/usr/bin/env python3
"""Opt-in real Claude Stop probe (uses configured model access; no agent tools).

This proves native context delivery only, not acceptance or cross-agent completion.
Run: python3 lince-messages/tests/probe-claude-intake.py [--output NEW_FIXTURE.json]
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import capabilities
from service import Server
from store import Store

ROOT = Path(__file__).resolve().parents[1]


def probe(executable):
    version = subprocess.check_output([executable, '--version'], text=True, timeout=10)
    version = re.search(r'\b\d+\.\d+\.\d+\b', version).group()
    with tempfile.TemporaryDirectory(prefix='lince-native-intake-') as directory:
        work = Path(directory)
        store = Store(work / 'db', 'probe-admin')

        def host(op, **args):
            return store.handle({'v': 1, 'token': 'probe-admin', 'op': 'host.' + op, 'args': args})

        actor = host('register', alias='Claude probe', agent='claude', capabilities=capabilities('claude', version))
        sender = host('register', alias='Fixture sender', agent='fixture')
        group = host('group', name='Native intake probe', members=[actor['instance'], sender['instance']])['group']
        host('automatic', instance=actor['instance'], enabled=True)
        request = store.handle({'v': 1, 'token': sender['token'], 'op': 'ask', 'args': {
            'recipient': actor['instance'], 'group': group, 'key': 'probe',
            'text': 'For this transport probe, do not use tools. Include LINCE_NATIVE_DELIVERY in your final '
                    'response. This tests receipt only, not completion.'}})['id']
        (work / 'credential').write_text(actor['token'])
        (work / 'credential').chmod(0o600)
        wrapper = work / 'capture.py'
        wrapper.write_text(f'''import json, pathlib, sys
sys.path.insert(0, {str(ROOT)!r})
from adapters import invoke
raw = json.load(sys.stdin)
keys = ('hook_event_name','session_id','stop_hook_active','permission_mode','source','agent_id','agent_type')
with pathlib.Path({str(work / 'events.jsonl')!r}).open('a') as output:
    output.write(json.dumps({{key: raw[key] for key in keys if key in raw}}) + '\\n')
result = invoke('claude', raw, {str(work / 'socket')!r}, {str(work / 'credential')!r})
if result:
    print(json.dumps(result))
''')
        settings = {'hooks': {event: [{'hooks': [{'type': 'command',
                    'command': f'{sys.executable} {wrapper}', 'timeout': 3}]}]
                    for event in ('SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd')}}
        (work / 'settings.json').write_text(json.dumps(settings))
        server = Server(work / 'socket', store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
        thread.start()
        try:
            env = {k: v for k, v in os.environ.items() if k not in ('CLAUDECODE', 'LINCE_AGENT_ID')
                   and not k.startswith('LINCE_MSG_')}
            result = subprocess.run([executable, '--settings', str(work / 'settings.json'), '--setting-sources', '',
                    '-p', '--max-turns', '3', '--tools', '', '--', 'Reply exactly LINCE_READY. Do not use tools.'],
                    cwd=work, env=env, capture_output=True, text=True, timeout=90)
            events = [json.loads(line) for line in (work / 'events.jsonl').read_text().splitlines()]
            stops = [e['stop_hook_active'] for e in events if e['hook_event_name'] == 'Stop']
            request_state = host('get', request=request)
            observed = result.returncode == 0 and 'LINCE_NATIVE_DELIVERY' in result.stdout
            assert observed and stops == [False, True], 'Native continuation not verified'
            assert request_state['delivery'] == 'delivered', request_state['delivery']
            return {'source': f'Real Claude Code {version} --print native Stop continuation on {sys.platform}.',
                    'result': 'Final response included LINCE_NATIVE_DELIVERY; tools disabled; no acceptance claimed.',
                    'events': events}
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output already exists; choose a new fixture path')
    evidence = probe(args.claude)
    if args.output:
        args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
