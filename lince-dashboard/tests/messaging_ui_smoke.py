"""Real Zellij/broker smoke with fixture agents, never a model-session claim."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lince-messages'))
from protocol import call


def check_messages(work, session, cli, wait_for, key, panes, visible, env, terminal, attention=True):
    host_command = [str(work / 'lince-msg-host'), '--session', session]

    def host(op, **args):
        result = subprocess.run([*host_command, 'request', op, '--json', json.dumps(args)],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    current = panes()
    agents = [next(p for p in current if f'fixture{i}' in p['title']) for i in (1, 2, 3)]
    actors = [host('register', alias=f'fixture{i}', agent='fixture', pane_ref=str(p['id']))
              for i, p in enumerate(agents, 1)]
    group = host('group', name='UI smoke', members=[a['instance'] for a in actors])['group']
    digest = hashlib.sha256(session.encode()).hexdigest()[:24]
    endpoint = Path(f'/tmp/lince-msg-{os.getuid()}') / digest / 'mailbox.sock'

    def rpc(actor, op, **args):
        return call(endpoint, actors[actor]['token'], op, args)

    def screen(ps, name):
        pane = ps.get(name)
        if not pane:
            return ''
        # dump-screen returns an empty string for WASM panes; observe the actual
        # client rendering through a terminal emulator instead.
        x, y = pane['pane_x'], pane['pane_y']
        return '\n'.join(line[x:x + pane['pane_columns']] for line in
                         terminal.display[y:y + pane['pane_rows']])

    def has(name, text):
        return lambda ps: text in screen(ps, name)

    def settled():
        wait_for(lambda ps: 'Cancel does not undo edits.' in screen(ps, 'lince-dialog'))

    key(b'\x1b1')
    wait_for(lambda ps: any(p['id'] == agents[0]['id'] and p['is_focused'] for p in ps.values() if not p['is_plugin']))
    request = rpc(0, 'delegate', recipient=actors[1]['instance'], group=group,
                  text='UI_SMOKE_TASK full request text', key='ui-task')['id']
    if attention:
        wait_for(has('lince-attention', 'Mail 1'))
    rpc(1, 'accept', request=request)
    if attention:
        wait_for(has('lince-attention', 'Work 1'))
    # Receiving/accepting on a hidden pane never reveals or focuses it.
    current = panes()
    assert next(p for p in current if not p['is_plugin'] and p['id'] == agents[0]['id'])['is_focused']
    assert next(p for p in current if not p['is_plugin'] and p['id'] == agents[1]['id'])['is_suppressed']
    key(b'\x1b2')
    wait_for(lambda ps: any(p['id'] == agents[1]['id'] and p['is_focused'] for p in ps.values() if not p['is_plugin']))
    if attention:
        wait_for(has('lince-attention', 'task'))
        wait_for(has('lince-attention', request[:8]))
    key(b'\x1bd')
    wait_for(visible('lince-dialog', True))
    key(b'm')
    wait_for(has('lince-dialog', 'UI_SMOKE_TASK'))
    settled()
    key(b'\r')
    wait_for(has('lince-dialog', 'Cancellation: not requested'))
    settled()
    key(b'p')
    wait_for(lambda ps: host('get', request=request)['work'] == 'paused')
    wait_for(has('lince-dialog', 'work paused'))
    settled()
    key(b'u')
    wait_for(has('lince-dialog', 'work active'))
    settled()
    key(b'c')
    wait_for(has('lince-dialog', 'acknowledgement pending'))
    settled()
    rpc(1, 'cancel-ack', request=request)
    key(b'r')
    wait_for(has('lince-dialog', 'Cancellation: acknowledged'))
    settled()
    # Explicit navigation is the only messaging operation that changes focus.
    key(b's')
    wait_for(lambda ps: any(p['id'] == agents[0]['id'] and p['is_focused'] for p in ps.values() if not p['is_plugin']))
    key(b'\x1bd')
    wait_for(visible('lince-dialog', True))
    key(b'm')
    wait_for(has('lince-dialog', 'UI_SMOKE_TASK'))
    settled()
    key(b'g')
    wait_for(has('lince-dialog', 'Communication groups'))
    key(b' ')
    wait_for(lambda ps: not any(m['instance'] == actors[0]['instance'] for m in host('snapshot')['members']))
    wait_for(has('lince-dialog', '[ ] fixture1'))
    key(b' ')
    wait_for(has('lince-dialog', '[x] fixture1'))
    # Close groups, mailbox and the existing agent menu separately.
    for _ in range(3):
        key(b'\x1b')
        # Wait for each view transition rather than sending a burst of escapes.
        if _ == 0:
            wait_for(has('lince-dialog', 'Messages and tasks'))
        elif _ == 1:
            wait_for(lambda ps: 'Messages and tasks' not in screen(ps, 'lince-dialog'))
        else:
            wait_for(visible('lince-dialog', False))
    for actor in actors:
        host('revoke', instance=actor['instance'])
    print('messaging: real broker, hidden recipient, thread controls, groups and explicit navigation OK'
          + ('; status line/provenance OK' if attention else ''))
