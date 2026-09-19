"""Exercise the real Pi/OpenCode extension callbacks without provider calls."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node required for native extension tests')
class PeerHooks(unittest.TestCase):
    def test_amp_observes_state_and_ignores_stale_thread_reads(self):
        self.run_hook(ROOT / 'hooks/amp-status-hook.js', '''
const handlers = {}; let dispose;
hook({on: (event, callback) => { handlers[event] = callback; }, onDispose: cb => {dispose = cb;}});
assert.equal(status(), 'amp.unknown');
let observer; let resolve; let unsubscribed = 0;
const state = {subscribe: o => { observer = o; return {unsubscribe: () => unsubscribed++}; },
    get: () => new Promise(r => {resolve = r;})};
const started = handlers['session.start']({}, {thread: {state}});
observer.next('running'); resolve('idle'); await started;
assert.equal(status(), 'amp.running');
observer.next('awaiting-approval'); assert.equal(status(), 'amp.awaiting-approval');
observer.next('idle'); assert.equal(status(), 'amp.idle');
observer.next('error'); assert.equal(status(), 'amp.error');
observer.next('invented'); assert.equal(status(), 'amp.unknown');
const previous = observer;
const switched = handlers['session.start']({}, {thread: {state}});
resolve('idle'); await switched;
previous.next('running'); assert.equal(status(), 'amp.idle');
observer.error(new Error()); assert.equal(status(), 'amp.unknown');
dispose(); observer.next('idle'); assert.equal(status(), 'amp.stopped');
assert.equal(unsubscribed, 2);
''')

    def run_hook(self, source, script):
        with tempfile.TemporaryDirectory() as directory:
            env = {k: v for k, v in os.environ.items() if not k.startswith('ZELLIJ')}
            env.update(LINCE_AGENT_ID='test-peer', LINCE_STATUS_DIR=directory)
            prelude = f"import hook from {str(source.as_uri())!r};\n"
            prelude += "import { readFileSync } from 'node:fs';\nimport assert from 'node:assert/strict';\n"
            prelude += "const status = () => readFileSync(process.env.LINCE_STATUS_DIR + '/test-peer.state','utf8');\n"
            result = subprocess.run(['node', '--experimental-strip-types', '--input-type=module', '-e', prelude + script],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_pi_writes_status_without_zellij_and_finishes_only_at_agent_end(self):
        self.run_hook(ROOT / 'hooks/pi/lince-pi-hook.ts', '''
const handlers = {};
hook({on: (event, callback) => { handlers[event] = callback; }});
handlers.session_start(); assert.equal(status(), 'session_start');
handlers.turn_start(); assert.equal(status(), 'turn_start');
handlers.tool_call(); assert.equal(status(), 'tool_call');
handlers.turn_end(); assert.equal(status(), 'turn_end');
let idle = false;
handlers.agent_end({}, {isIdle: () => idle}); assert.equal(status(), 'turn_end');
idle = true;
await new Promise(resolve => setTimeout(resolve, 80)); assert.equal(status(), 'agent_end');
handlers.agent_settled({}, {isIdle: () => true});
await new Promise(resolve => setTimeout(resolve, 80)); assert.equal(status(), 'agent_settled');
handlers.agent_end({}, {isIdle: () => true});
handlers.turn_start();
await new Promise(resolve => setTimeout(resolve, 80)); assert.equal(status(), 'turn_start');
handlers.session_shutdown(); assert.equal(status(), 'session_shutdown');
''')

    def test_opencode_unknown_status_is_not_idle(self):
        self.run_hook(ROOT / 'hooks/opencode-status-hook.js', '''
const plugin = await hook({directory: '.'});
for (const state of ['busy', 'idle', 'retry', undefined]) {
    await plugin.event({event: {type: 'session.status', properties: {status: {type: state}}}});
    assert.equal(status(), 'session.status.' + (state === 'busy' || state === 'idle' ? state : 'unknown'));
}
await plugin.event({event: {type: 'session.idle'}}); assert.equal(status(), 'session.idle');
await plugin.event({event: {type: 'session.deleted'}}); assert.equal(status(), 'session.deleted');
''')


if __name__ == '__main__': unittest.main()
