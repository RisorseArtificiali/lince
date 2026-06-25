"""MacosBackend — the Apple-Silicon macOS-guest substrate glue (Epic #268).

Drives ``tart`` (cirruslabs, over Virtualization.framework) for every
:class:`~lince_lab.backend.Backend` operation, reaching the guest over SSH
(``tart ip`` + password auth via ``SSH_ASKPASS``). It is the macOS sibling of
:mod:`lince_lab.lima_backend`: the broker / policy / recipe / bisect / capture
layers are unchanged; only this substrate glue differs.

Key differences from Lima/QEMU:

* ``tart run`` is a FOREGROUND process (the VM runs for as long as it lives), so
  :meth:`start` spawns it detached and tracks it; :meth:`stop`/:meth:`delete`
  tear it down (authoritatively via ``tart stop``/``tart delete``).
* Virtualization.framework has no snapshots → :meth:`snapshot_create` /
  :meth:`snapshot_apply` are emulated with APFS copy-on-write ``tart clone`` of a
  STOPPED golden guest (named ``<vm>__snap__<tag>``).
* ``exec``/``copy_*`` go over SSH/scp to ``tart ip`` (no ``limactl shell``).

Lifecycle verbs route through :meth:`MacosBackend._run`, which raises
:class:`~lince_lab.errors.BackendError` on a nonzero ``tart`` exit. ``exec`` is
kept separate so it returns the guest code without raising — that is the bisect
signal.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from lince_lab.backend import (
    Backend,
    CaptureChannel,
    ExecResult,
    VmState,
    VmStatus,
)
from lince_lab.errors import BackendError

# The stdio-pipe capture channel is backend-neutral; reuse it to stay DRY. A
# rename/extract to a neutral module is tracked for #266, where macOS capture is
# first exercised.
from lince_lab.lima_backend import LimaCaptureChannel

# The tart executable, resolved on PATH (installed via `brew install
# cirruslabs/cli/tart`). Kept as a constant so tests can assert on argv[0].
TART = "tart"

# Tart base-image convention: the guest admin user + password. NOT a secret — it
# is the public default of the cirruslabs images, used only to bootstrap SSH into
# a disposable guest. No host credential is ever forwarded.
GUEST_USER = "admin"
GUEST_PASSWORD = "admin"

# Disposable in-guest path the host-side ht is copied to (matches the Lima glue).
GUEST_HT_PATH = "/tmp/lince-lab-ht"

# Separator for clone-based snapshot guests: "<vm>__snap__<tag>". Chosen to never
# collide with the lince-lab- VM-name prefix policy.
SNAP_SEP = "__snap__"

# macOS guests need more than the Linux-tuned config defaults (a 2 GiB guest will
# not boot macOS reliably). `tart set --memory` is absolute, so without a floor we
# would DOWNGRADE the base image below a bootable size — floor the caps here.
MIN_MACOS_CPU = 2
MIN_MACOS_MEMORY_MB = 4096


def _mem_to_mb(spec: str) -> int:
    """Parse a memory size string (e.g. ``"2GiB"``) into whole MB for ``tart set``."""
    s = str(spec).strip().lower()
    if s.endswith("gib"):
        return int(float(s[:-3]) * 1024)
    if s.endswith("mib"):
        return int(float(s[:-3]))
    if s.endswith("gb"):
        return int(float(s[:-2]) * 1000)
    if s.endswith("mb"):
        return int(float(s[:-2]))
    return int(float(s))  # bare number → assume MB


def _map_state(raw: str) -> VmStatus:
    """Map a ``tart list`` State string to :class:`VmStatus` (running → RUNNING)."""
    return VmStatus.RUNNING if raw.strip().lower() == "running" else VmStatus.STOPPED


def _host_ht_path() -> str:
    """Resolve the HOST-side macOS/arm64 ``ht`` binary the broker copies into a guest.

    Honors ``$LINCE_LAB_HT`` if set; otherwise the lince-lab share dir's
    ``bin/ht-darwin`` (``$XDG_DATA_HOME`` then ``$HOME/.local/share``), matching
    the install/update scripts. Not required to exist — :meth:`open_capture`
    checks for it and falls back to a bare guest ``ht`` on PATH.
    """
    env = os.environ.get("LINCE_LAB_HT")
    if env:
        return str(Path(env).expanduser())
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return str((base / "lince" / "lince-lab" / "bin" / "ht-darwin").expanduser())


class MacosBackend(Backend):
    """Real :class:`Backend` that drives ``tart`` (macOS guests on Apple Silicon)."""

    def __init__(self, tart: str = TART) -> None:
        self._tart = tart
        self._host_ht = _host_ht_path()
        # Tracks detached `tart run` processes by VM name so stop/delete can reap them.
        self._running: dict[str, subprocess.Popen] = {}
        # Lazily created askpass helper (see _askpass_path).
        self._askpass: str | None = None

    # ── one lifecycle shell-out helper (raises on nonzero) ───────────────────
    def _run(
        self, argv: list[str], *, stdin: str | None = None, stream: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """Run a ``tart`` command, raising :class:`BackendError` on a nonzero exit."""
        if stream:
            proc = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE, stderr=None, text=True)
        else:
            proc = subprocess.run(argv, input=stdin, capture_output=True, text=True)
        if proc.returncode != 0:
            cmd = " ".join(argv)
            detail = "(see the tart output above)" if stream else (proc.stderr or "").strip()
            raise BackendError(f"{cmd} failed (exit {proc.returncode}): {detail}")
        return proc

    # ── lifecycle ────────────────────────────────────────────────────────────
    def create(self, name: str, template_yaml: str) -> None:
        # The broker passes the policy-forced template JSON. We interpret it for
        # the macOS substrate: images[0].location is the Tart OCI ref; cpus/memory
        # map to `tart set`. (plain/mounts/ssh are Lima-only and ignored — Tart
        # guests expose no host fs and inject no host keys by default.)
        try:
            spec = json.loads(template_yaml)
        except json.JSONDecodeError as exc:
            raise BackendError(f"macOS create: template is not JSON: {exc}") from exc
        images = spec.get("images") or []
        location = images[0].get("location") if images and isinstance(images[0], dict) else None
        if not location:
            raise BackendError("macOS create: template has no images[0].location (Tart OCI ref)")
        # `tart clone <oci-ref> <name>` pulls the image if not already cached.
        self._run([self._tart, "clone", str(location), name], stream=True)
        # Apply resource caps, floored to macOS-sane minimums (see MIN_MACOS_*).
        cpus = int(spec["cpus"]) if spec.get("cpus") is not None else MIN_MACOS_CPU
        mem_mb = _mem_to_mb(str(spec["memory"])) if spec.get("memory") is not None else MIN_MACOS_MEMORY_MB
        set_argv = [
            self._tart,
            "set",
            name,
            "--cpu",
            str(max(cpus, MIN_MACOS_CPU)),
            "--memory",
            str(max(mem_mb, MIN_MACOS_MEMORY_MB)),
        ]
        # disk is grow-only in Tart; the base image's disk is sufficient — skip it.
        self._run(set_argv)

    def start(self, name: str) -> None:
        # `tart run` is a FOREGROUND process; spawn it detached (its own session)
        # and keep the handle so stop/delete can reap it. Output is discarded — the
        # VM's console is not our channel (we talk to it over SSH).
        print(
            f"lince-lab: starting macOS guest {name!r} via tart — first boot of a fresh clone can take a minute…",
            file=sys.stderr,
            flush=True,
        )
        proc = subprocess.Popen(
            [self._tart, "run", name, "--no-graphics"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._running[name] = proc
        # macOS first boot + sshd coming up can be slow; give it a generous window.
        deadline = time.monotonic() + 300.0
        # First wait for a DHCP lease (the guest networked), then for sshd to answer
        # — `tart ip` returns before sshd is ready, so an exec right after start
        # would otherwise hit "connection refused".
        ip = self._wait_for_ip(name, deadline)
        self._wait_for_ssh(name, ip, deadline)

    def stop(self, name: str, force: bool = False) -> None:
        # `tart stop` is authoritative (it halts the VM regardless of who launched
        # the run process); a forced stop shortens the graceful-shutdown timeout.
        argv = [self._tart, "stop", name]
        if force:
            argv += ["-t", "0"]
        try:
            self._run(argv)
        finally:
            self._reap(name)

    def delete(self, name: str, force: bool = False) -> None:
        # A running VM cannot be deleted; best-effort stop first, then delete.
        try:
            self._run([self._tart, "stop", name])
        except BackendError:
            pass
        self._reap(name)
        self._run([self._tart, "delete", name])

    def _reap(self, name: str) -> None:
        proc = self._running.pop(name, None)
        if proc is None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            pass

    def status(self, name: str) -> VmState:
        for rec in self._list_records():
            if str(rec.get("Name", "")) == name:
                return VmState(
                    name=name,
                    status=_map_state(str(rec.get("State", ""))),
                    snapshots=self._safe_snapshot_list(name),
                )
        return VmState(name=name, status=VmStatus.ABSENT, snapshots=[])

    def list(self) -> list[VmState]:
        states: list[VmState] = []
        for rec in self._list_records():
            nm = str(rec.get("Name", ""))
            # Skip pullable base images (Source=OCI) and our golden snapshot clones
            # (an implementation detail) — neither is a user-facing lab VM.
            if str(rec.get("Source", "")).upper() == "OCI":
                continue
            if SNAP_SEP in nm:
                continue
            states.append(
                VmState(
                    name=nm,
                    status=_map_state(str(rec.get("State", ""))),
                    snapshots=self._safe_snapshot_list(nm),
                )
            )
        return states

    def _list_records(self) -> list[dict]:
        """Run ``tart list --format json`` → parsed list of VM records."""
        proc = self._run([self._tart, "list", "--format", "json"])
        try:
            data = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            return []
        return [r for r in data if isinstance(r, dict)]

    def _safe_snapshot_list(self, name: str) -> list[str]:
        try:
            return self.snapshot_list(name)
        except BackendError:
            return []

    def _wait_for_ip(self, name: str, deadline: float) -> str:
        """Poll ``tart ip`` until the guest has an address or the deadline passes."""
        last = ""
        while time.monotonic() < deadline:
            proc = subprocess.run([self._tart, "ip", name], capture_output=True, text=True)
            ip = (proc.stdout or "").strip()
            if proc.returncode == 0 and ip:
                return ip
            last = (proc.stderr or "").strip()
            # Short poll backoff on the readiness signal (the lease), not a fixed
            # sleep of the workload — mirrors the broker-readiness poll in 00-lib.sh.
            time.sleep(1.0)
        raise BackendError(f"timed out waiting for {name!r} to get an IP: {last}")

    def _wait_for_ssh(self, name: str, ip: str, deadline: float) -> None:
        """Poll an ssh probe until the guest's sshd answers or the deadline passes."""
        last = ""
        probe = ["ssh", *self._ssh_opts(), f"{GUEST_USER}@{ip}", "true"]
        while time.monotonic() < deadline:
            proc = subprocess.run(
                probe,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=self._ssh_env(),
            )
            if proc.returncode == 0:
                return
            last = (proc.stderr or "").strip()
            # Short backoff on the readiness signal (sshd answering), not a fixed
            # sleep of any workload.
            time.sleep(2.0)
        raise BackendError(f"timed out waiting for ssh on {name!r} ({ip}): {last}")

    def _ip(self, name: str) -> str:
        proc = subprocess.run([self._tart, "ip", name], capture_output=True, text=True)
        ip = (proc.stdout or "").strip()
        if proc.returncode != 0 or not ip:
            raise BackendError(f"no IP for {name!r} (is it running?): {(proc.stderr or '').strip()}")
        return ip

    # ── SSH transport ────────────────────────────────────────────────────────
    def _ssh_opts(self) -> list[str]:
        # Disposable guests get a fresh host key + ephemeral IP each boot, so do
        # not persist/verify host keys (avoids prompts and known_hosts churn).
        return [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "PreferredAuthentications=password,keyboard-interactive",
            "-o",
            "NumberOfPasswordPrompts=1",
        ]

    def _askpass_path(self) -> str:
        """Lazily create a tiny askpass helper that echoes the guest password.

        Used with ``SSH_ASKPASS`` / ``SSH_ASKPASS_REQUIRE=force`` so password auth
        works non-interactively (the password is the public Tart default, not a
        secret). Created 0700 under the temp dir, once per process.
        """
        if self._askpass and os.path.isfile(self._askpass):
            return self._askpass
        fd, path = tempfile.mkstemp(prefix="lince-lab-askpass-")
        with os.fdopen(fd, "w") as f:
            f.write(f"#!/bin/sh\necho {shlex.quote(GUEST_PASSWORD)}\n")
        os.chmod(path, 0o700)
        self._askpass = path
        return path

    def _ssh_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["SSH_ASKPASS"] = self._askpass_path()
        env["SSH_ASKPASS_REQUIRE"] = "force"
        # Some ssh builds gate askpass on DISPLAY; harmless to set when unset.
        env.setdefault("DISPLAY", ":0")
        return env

    @staticmethod
    def _remote_command(argv: list[str], workdir: str | None, env: dict[str, str] | None) -> str:
        """Build a single shell-quoted remote command string (no host word-split)."""
        prefix = ""
        if workdir is not None:
            prefix += f"cd {shlex.quote(workdir)} && "
        if env:
            prefix += "env " + " ".join(f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items()) + " "
        return prefix + " ".join(shlex.quote(a) for a in argv)

    # ── exec (exit code propagates, never raises on guest nonzero) ───────────
    def exec(
        self,
        name: str,
        argv: list[str],
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        ip = self._ip(name)
        remote = self._remote_command(argv, workdir, env)
        cmd = ["ssh", *self._ssh_opts(), f"{GUEST_USER}@{ip}", remote]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=self._ssh_env(),
        )
        # CRITICAL: return the guest exit code verbatim; do NOT raise — the bisect
        # signal. (ssh returns the remote command's exit code on a live channel.)
        return ExecResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def _run_ssh(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        """Run an ssh/scp command with askpass env, raising on a nonzero exit."""
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=self._ssh_env(),
        )
        if proc.returncode != 0:
            raise BackendError(f"{argv[0]} failed (exit {proc.returncode}): {(proc.stderr or '').strip()}")
        return proc

    def copy_in(self, name: str, host_path: str, guest_path: str, recursive: bool = False) -> None:
        ip = self._ip(name)
        argv = ["scp", *self._ssh_opts()]
        if recursive:
            argv.append("-r")
        argv += [host_path, f"{GUEST_USER}@{ip}:{guest_path}"]
        self._run_ssh(argv)

    def copy_out(self, name: str, guest_path: str, host_path: str, recursive: bool = False) -> None:
        ip = self._ip(name)
        argv = ["scp", *self._ssh_opts()]
        if recursive:
            argv.append("-r")
        argv += [f"{GUEST_USER}@{ip}:{guest_path}", host_path]
        self._run_ssh(argv)

    # ── snapshots (clone-based: vz has no loadvm) ────────────────────────────
    def _golden(self, name: str, tag: str) -> str:
        return f"{name}{SNAP_SEP}{tag}"

    def snapshot_create(self, name: str, tag: str) -> None:
        golden = self._golden(name, tag)
        # A clean golden requires a STOPPED source (cloning a live VM is only
        # crash-consistent). Stop if running, clone, then restore the run state.
        was_running = self.status(name).status == VmStatus.RUNNING
        if was_running:
            self.stop(name)
        if tag in self.snapshot_list(name):
            self._run([self._tart, "delete", golden])  # overwrite an existing tag
        self._run([self._tart, "clone", name, golden])
        if was_running:
            self.start(name)

    def snapshot_apply(self, name: str, tag: str) -> None:
        # The per-candidate bisect reset: rebuild `name` from the golden clone.
        if tag not in self.snapshot_list(name):
            raise BackendError(f"no snapshot {tag!r} for {name!r}")
        golden = self._golden(name, tag)
        self.stop(name, force=True)
        self._run([self._tart, "delete", name])
        self._run([self._tart, "clone", golden, name])
        self.start(name)

    def snapshot_delete(self, name: str, tag: str) -> None:
        self._run([self._tart, "delete", self._golden(name, tag)])

    def snapshot_list(self, name: str) -> list[str]:
        prefix = f"{name}{SNAP_SEP}"
        tags: list[str] = []
        for rec in self._list_records():
            nm = str(rec.get("Name", ""))
            if nm.startswith(prefix):
                tags.append(nm[len(prefix) :])
        return tags

    # ── capture (ht inside the guest, driven over SSH) ───────────────────────
    def open_capture(self, name: str, argv: list[str], cols: int, rows: int) -> CaptureChannel:
        # Ship the macOS/arm64 ht into the guest when present, else fall back to a
        # bare `ht` on the guest PATH. Copying our own disposable capture driver
        # into a disposable guest does not widen host access.
        if os.path.isfile(self._host_ht):
            self.copy_in(name, self._host_ht, GUEST_HT_PATH)
            ip0 = self._ip(name)
            self._run_ssh(["ssh", *self._ssh_opts(), f"{GUEST_USER}@{ip0}", f"chmod +x {GUEST_HT_PATH}"])
            guest_ht = GUEST_HT_PATH
        else:
            guest_ht = "ht"
        ip = self._ip(name)
        remote = f"{guest_ht} --size {cols}x{rows} --subscribe init,output,snapshot -- " + " ".join(
            shlex.quote(a) for a in argv
        )
        cmd = ["ssh", *self._ssh_opts(), f"{GUEST_USER}@{ip}", remote]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self._ssh_env(),
            start_new_session=True,
        )
        return LimaCaptureChannel(proc, argv=cmd)

    # ── egress policy ────────────────────────────────────────────────────────
    def apply_egress_lockdown(
        self, name: str, allow_ips: list[str], allow_ports: list[int], timeout: float = 180.0
    ) -> None:
        # Egress control for macOS guests uses pfctl, not Linux nft — that belongs
        # to the Seatbelt-recipe work (#266). For the #263 adapter we DEFER it with
        # a clear warning rather than run the (Linux-only) nft script, which would
        # fail-closed on a macOS guest and abort `vm up`. The guest therefore
        # retains network access until #266 lands pfctl enforcement.
        print(
            f"lince-lab: WARNING macOS egress lock-down not yet enforced for {name!r} "
            "(deferred to #266; guest egress is NOT restricted)",
            file=sys.stderr,
            flush=True,
        )
