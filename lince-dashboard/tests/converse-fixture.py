#!/usr/bin/env python3
"""Tiny bracketed-paste terminal fixture; never a real-agent validation claim."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import termios
import tty

work = Path.cwd()
pane = os.environ['ZELLIJ_PANE_ID']
(work / f'pid-{pane}').write_text(str(os.getpid()))
state = work / f'fixture-{pane}.state'
state.write_text('Stop')
saved = termios.tcgetattr(0)
tty.setraw(0)
os.write(1, b'\x1b[?2004hREADY\r\n')
buffer = b''
try:
    while True:
        byte = os.read(0, 1)
        if not byte:
            break
        if byte != b'\r':
            buffer += byte
            continue
        prompt = buffer.decode().removeprefix('\x1b[200~').removesuffix('\x1b[201~')
        buffer = b''
        os.write(1, b'RECEIVED\r\n')
        with (work / f'received-{pane}.jsonl').open('a') as log:
            log.write(json.dumps(prompt) + '\n')
        config = work / f'peer-{pane}.json'
        if 'UI_SMOKE_QUESTION' in prompt and config.exists():
            peer = json.loads(config.read_text())
            conversation = re.search(r'conversation ([a-f0-9]{8})', prompt)[1]
            sender = re.search(r'Reply with: lince-msg send ([a-f0-9]+)', prompt)[1]
            env = {**os.environ, 'LINCE_MSG_ENDPOINT': peer['endpoint'], 'LINCE_MSG_CREDENTIAL': peer['credential']}
            result = subprocess.run([str(work / 'lince-msg'), 'send', sender, '--conversation', conversation,
                                     '--text', 'UI_SMOKE_ANSWER Regarding 17+25: 42'], env=env, capture_output=True)
            if result.returncode:
                (work / f'error-{pane}').write_bytes(result.stdout + result.stderr)
        state.write_text('Stop')
finally:
    termios.tcsetattr(0, termios.TCSANOW, saved)
