"""Actual Zellij injection and asynchronous reply with terminal fixtures, no model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lince-messages'))
from protocol import call


def check_messages(work, session, cli, wait_for, key, panes, visible, env, terminal, attention=True):
    def host(op, **args):
        result = subprocess.run([str(work / 'lince-msg-host'), '--session', session, 'request', op,
                                 '--json', json.dumps(args)], env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    agents = [next(p for p in panes() if f'fixture{i}' in p['title']) for i in (1, 2, 3)]
    actors = []
    digest = hashlib.sha256(session.encode()).hexdigest()[:24]
    endpoint = Path(f'/tmp/lince-msg-{os.getuid()}') / digest / 'mailbox.sock'
    for index, pane in enumerate(agents, 1):
        pid = pane['id']
        wait_for(lambda ps: (work / f'pid-{pid}').exists())
        actor = host('register', alias=f'fixture{index}', agent=('claude', 'pi', 'opencode')[index - 1], pane_ref=str(pid),
                     status_id=f'fixture-{pid}', status_dir=str(work), pid=int((work / f'pid-{pid}').read_text()))
        actors.append(actor)
        token = work / f'token-{pid}'
        token.write_text(actor['token'])
        (work / f'peer-{pid}.json').write_text(json.dumps({'endpoint': str(endpoint), 'credential': str(token)}))
        (work / f'fixture-{pid}.state').write_text('Stop')

    def screen(ps, name):
        pane = ps.get(name)
        if not pane: return ''
        x, y = pane['pane_x'], pane['pane_y']
        return '\n'.join(line[x:x + pane['pane_columns']] for line in terminal.display[y:y + pane['pane_rows']])

    def has(name, text):
        return lambda ps: text in screen(ps, name)

    # Both peers are busy: send must return immediately and preserve the recipient's input.
    for pane in agents[:2]: (work / f"fixture-{pane['id']}.state").write_text('PreToolUse')
    before = next(p['id'] for p in panes() if p['is_focused'])
    result = call(endpoint, actors[0]['token'], 'send', {'recipient': actors[1]['instance'],
                    'text': 'UI_SMOKE_QUESTION What is 17+25?\nReply to the sender.'})
    assert result['status'] == 'pending'
    assert not (work / f"received-{agents[1]['id']}.jsonl").exists()
    # Existing idle status causes a real paste + Enter in the hidden recipient.
    (work / f"fixture-{agents[1]['id']}.state").write_text('agent_end')
    wait_for(lambda ps: len(host('snapshot')['messages']) == 2)
    messages = host('snapshot')['messages']
    assert messages[0]['status'] == 'submitted', messages
    assert messages[1]['status'] == 'pending', messages
    assert messages[1]['conversation'] == result['conversation']
    assert next(p['id'] for p in panes() if p['is_focused']) == before
    assert not (work / f"received-{agents[0]['id']}.jsonl").exists()
    (work / f"fixture-{agents[0]['id']}.state").write_text('Stop')
    wait_for(lambda ps: all(m['status'] == 'submitted' for m in host('snapshot')['messages']))
    received = (work / f"received-{agents[0]['id']}.jsonl").read_text()
    assert 'UI_SMOKE_ANSWER' in received and result['conversation'] in received
    assert next(p['id'] for p in panes() if p['is_focused']) == before
    # OpenCode uses its own idle event; the same text transport must work.
    (work / f"fixture-{agents[2]['id']}.state").write_text('session.status.idle')
    second = call(endpoint, actors[0]['token'], 'send', {'recipient': actors[2]['instance'],
                   'text': 'UI_SMOKE_QUESTION OpenCode path: 17+25?'})
    wait_for(lambda ps: len(host('snapshot')['messages']) == 4
             and all(m['status'] == 'submitted' for m in host('snapshot')['messages']))
    assert 'UI_SMOKE_ANSWER' in (work / f"received-{agents[0]['id']}.jsonl").read_text()
    result = second
    # Reuse the third fixture as each newly integrated provider. These are
    # transport checks with native event names, not real-provider TUI tests.
    for provider, busy, idle in [('gemini', 'gemini.ToolPermission', 'gemini.AfterAgent'),
                                  ('amp', 'amp.awaiting-approval', 'amp.idle'),
                                  ('goose', 'goose.PreToolUse', 'goose.Stop')]:
        pid = agents[2]['id']
        actor = host('register', alias='fixture3', agent=provider, pane_ref=str(pid),
                     status_id=f'fixture-{pid}', status_dir=str(work), pid=int((work / f'pid-{pid}').read_text()))
        actors.append(actor)
        (work / f'token-{pid}').write_text(actor['token'])
        state = work / f'fixture-{pid}.state'
        state.write_text(busy)
        count = len(host('snapshot')['messages'])
        result = call(endpoint, actors[0]['token'], 'send', {'recipient': actor['instance'],
                      'text': f'UI_SMOKE_QUESTION {provider} path: 17+25?'})
        assert result['status'] == 'pending'
        state.write_text(idle)
        wait_for(lambda ps: len(host('snapshot')['messages']) == count + 2
                 and all(m['status'] == 'submitted' for m in host('snapshot')['messages']))
        assert next(p['id'] for p in panes() if p['is_focused']) == before
    key(b'\x1b1')
    if attention:
        wait_for(has('lince-attention', result['conversation']))
    key(b'\x1bd')
    wait_for(visible('lince-dialog', True))
    wait_for(has('lince-dialog', 'Messages'))
    key(b'm')
    wait_for(has('lince-dialog', 'UI_SMOKE_ANSWER'))
    key(b'\r')
    wait_for(has('lince-dialog', 'Text and Enter sent'))
    assert 'groups' not in screen({p['title']: p for p in panes()}, 'lince-dialog')
    for _ in range(3):
        key(b'\x1b')
        if _ == 0: wait_for(has('lince-dialog', 'Pane conversations'))
        elif _ == 1: wait_for(lambda ps: 'Pane conversations' not in screen(ps, 'lince-dialog'))
        else: wait_for(visible('lince-dialog', False))
    for actor in actors: host('revoke', instance=actor['instance'])
    print('conversations: real paste/Enter, busy queue, asynchronous reply, correlation, unchanged focus and UI OK')
