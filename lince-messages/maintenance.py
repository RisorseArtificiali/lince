"""Stop this user's authenticated mailboxes before replacing/removing their code."""
from pathlib import Path
import os
import re
import sys
import time

from protocol import ProtocolError, call


def stop_all():
    root = Path.home() / ".local/state/lince-messages/sessions"
    failed = False
    if not root.exists():
        return 0
    for private in root.iterdir():
        if not re.fullmatch(r"[0-9a-f]{24}", private.name) or private.is_symlink() or not private.is_dir():
            continue
        token_file = private / "admin.token"
        endpoint = Path(f"/tmp/lince-msg-{os.getuid()}") / private.name / "mailbox.sock"
        if not endpoint.is_socket():
            continue
        if token_file.is_symlink():
            failed = True
            continue
        try:
            token = token_file.read_text().strip()
            call(endpoint, token, "host.shutdown")
            deadline = time.monotonic() + 6
            while endpoint.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            if endpoint.exists():
                failed = True
        except (FileNotFoundError, ConnectionRefusedError):
            # A stale socket is cleaned up by the next supervised launch.
            pass
        except (OSError, ProtocolError):
            failed = True
    if failed:
        print("Could not stop every mailbox; close active LINCE sessions before retrying.", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(stop_all())
