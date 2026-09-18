"""Trusted launch/controller helpers. Never expose the admin credential to agents."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from protocol import ProtocolError, call, require
from service import private_directory


class Supervisor:
    def __init__(self, session: str):
        require(bool(session), message="A host session name is required")
        self.key = hashlib.sha256(session.encode()).hexdigest()[:24]
        self.root = Path.home() / ".local/state/lince-messages"
        self.private = self.root / "sessions" / self.key
        self.public = Path(f"/tmp/lince-msg-{os.getuid()}") / self.key
        self.endpoint = self.public / "mailbox.sock"

    def rpc(self, operation, **args):
        token = (self.private / "admin.token").read_text().strip()
        return call(self.endpoint, token, "host." + operation, args)

    def ensure(self):
        for directory in (self.root, self.root / "sessions", self.private, self.root / "credentials",
                          self.public.parent, self.public):
            private_directory(directory)
        try:
            return self.rpc("ping")
        except (OSError, ProtocolError):
            pass
        log = self.private / "service.log"
        with log.open("ab") as output:
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("service.py")),
                "--private", str(self.private), "--public", str(self.public)],
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                return self.rpc("ping")
            except (OSError, ProtocolError):
                time.sleep(0.05)
        # Only terminate the process we just started; another start may have won the lock.
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise ProtocolError("unavailable", "Messaging service did not start; inspect its private service.log")

    def run(self, alias, agent, command, capabilities=None):
        self.ensure()
        instance = self.rpc("register", alias=alias, agent=agent, capabilities=capabilities or {})
        credential = self.root / "credentials" / (instance["instance"] + ".token")
        fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(instance["token"])
        env = {key: value for key, value in os.environ.items() if not key.startswith("LINCE_MSG_")}
        env.update(LINCE_MSG_ENDPOINT=str(self.endpoint), LINCE_MSG_CREDENTIAL=str(credential))
        child = None
        previous = {}

        def forward(signum, _frame):
            if child is not None and child.poll() is None:
                child.send_signal(signum)

        try:
            for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                previous[signum] = signal.signal(signum, forward)
            child = subprocess.Popen(command, env=env)
            returncode = child.wait()
            return returncode if returncode >= 0 else 128 - returncode
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            try:
                self.rpc("revoke", instance=instance["instance"])
            except (OSError, ProtocolError):
                pass
            credential.unlink(missing_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default=os.environ.get("ZELLIJ_SESSION_NAME"))
    sub = parser.add_subparsers(dest="op", required=True)
    sub.add_parser("ensure")
    request = sub.add_parser("request", help="Host-only typed operation; JSON arguments read from stdin")
    request.add_argument("operation")
    run = sub.add_parser("run", help="Launch an original agent TUI with a fresh messaging identity")
    run.add_argument("--alias", required=True)
    run.add_argument("--agent", required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        supervisor = Supervisor(args.session)
        if args.op == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            require(bool(command), message="Missing agent command")
            return supervisor.run(args.alias, args.agent, command)
        supervisor.ensure()
        result = supervisor.rpc(args.operation, **json.load(sys.stdin)) if args.op == "request" else {"ready": True}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, ProtocolError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "unavailable"), "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
