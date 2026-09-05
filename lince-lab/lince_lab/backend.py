"""Backend interface — the single seam everything else depends on (blueprint §2).

A :class:`Backend` abstracts the VM substrate. ``LimaBackend`` (real, KVM-only)
and ``FakeBackend`` (in-memory, deterministic) implement it; the same contract
suite runs against both, guaranteeing the Fake is a faithful stand-in so all
broker/recipe/bisect/capture logic is testable with no VM.

Only the dataclasses and the two ABCs live here. Concrete backends live in
``lima_backend.py`` / ``fake_backend.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class VmStatus(str, Enum):
    """Lifecycle state of a lab VM.

    ``str``-valued so it serializes straight to JSON as its value.
    """

    ABSENT = "absent"
    STOPPED = "stopped"
    RUNNING = "running"


@dataclass
class ExecResult:
    """Result of running a command in the guest.

    ``exit_code`` propagates verbatim (a nonzero guest exit is data, not an
    error) — it is the oracle/bisect signal.
    """

    exit_code: int
    stdout: str
    stderr: str


@dataclass
class VmState:
    """Observable state of a single VM."""

    name: str
    status: VmStatus
    snapshots: list[str] = field(default_factory=list)


class CaptureChannel(ABC):
    """A long-lived duplex line channel to a terminal-capture process in the VM.

    The concrete transport (``ht`` over ``limactl shell`` for Lima, an in-process
    scripted terminal for Fake) is hidden behind three methods. Messages are
    plain dicts; the channel handles framing.
    """

    @abstractmethod
    def send_line(self, obj: dict) -> None:
        """Send one command object to the capture process."""
        ...

    @abstractmethod
    def read_line(self, deadline: float) -> dict | None:
        """Read one event object, blocking until ``deadline`` (monotonic clock).

        Returns the next event dict, or ``None`` if ``deadline`` is reached with
        no event available. ``deadline`` is an absolute ``time.monotonic()``
        value; this is the no-sleep primitive the wait loops build on.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the channel and release its resources."""
        ...

    def diagnostics(self) -> str:
        """Return a human-readable diagnostic blob for failure messages.

        Concrete transports override this to surface what the capture process
        actually did — its argv, exit status, and the tail of its stderr/stdout —
        so a capture timeout reports *why* (e.g. ``ht: command not found``) rather
        than a bare deadline. The default is empty (in-process test channels have
        nothing useful to add)."""
        return ""


class Backend(ABC):
    """The VM substrate contract. Methods map 1:1 to broker verbs."""

    # ── lifecycle ───────────────────────────────────────────────────────────
    @abstractmethod
    def create(self, name: str, template_yaml: str) -> None:
        """Create (but do not start) a VM ``name`` from ``template_yaml``."""
        ...

    @abstractmethod
    def start(self, name: str) -> None:
        """Boot the VM ``name`` (must already exist)."""
        ...

    @abstractmethod
    def stop(self, name: str, force: bool = False) -> None:
        """Stop the VM ``name``; ``force`` requests a hard stop."""
        ...

    @abstractmethod
    def delete(self, name: str, force: bool = False) -> None:
        """Delete the VM ``name``; ``force`` deletes even if running."""
        ...

    @abstractmethod
    def status(self, name: str) -> VmState:
        """Return the current :class:`VmState` of ``name`` (ABSENT if unknown)."""
        ...

    @abstractmethod
    def list(self) -> list[VmState]:
        """Return the state of every VM this backend knows about."""
        ...

    # ── exec / files (exit code propagates) ──────────────────────────────────
    @abstractmethod
    def exec(
        self,
        name: str,
        argv: list[str],
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        """Run ``argv`` in the guest, returning its :class:`ExecResult`.

        A nonzero guest exit is returned, never raised — it is the bisect signal.
        """
        ...

    @abstractmethod
    def copy_in(self, name: str, host_path: str, guest_path: str, recursive: bool = False) -> None:
        """Copy ``host_path`` (host) into ``guest_path`` (guest)."""
        ...

    @abstractmethod
    def copy_out(self, name: str, guest_path: str, host_path: str, recursive: bool = False) -> None:
        """Copy ``guest_path`` (guest) out to ``host_path`` (host)."""
        ...

    # ── snapshots (bisect reset core) ────────────────────────────────────────
    @abstractmethod
    def snapshot_create(self, name: str, tag: str) -> None:
        """Create snapshot ``tag`` of VM ``name``."""
        ...

    @abstractmethod
    def snapshot_apply(self, name: str, tag: str) -> None:
        """Restore VM ``name`` to snapshot ``tag``."""
        ...

    @abstractmethod
    def snapshot_delete(self, name: str, tag: str) -> None:
        """Delete snapshot ``tag`` of VM ``name``."""
        ...

    @abstractmethod
    def snapshot_list(self, name: str) -> list[str]:
        """Return the snapshot tags of VM ``name``."""
        ...

    # ── capture transport ────────────────────────────────────────────────────
    @abstractmethod
    def open_capture(self, name: str, argv: list[str], cols: int, rows: int) -> CaptureChannel:
        """Open a :class:`CaptureChannel` wrapping ``argv`` at grid ``cols``x``rows``."""
        ...

    # ── egress policy (concrete default; OS-specific backends override) ───────
    def apply_egress_lockdown(
        self, name: str, allow_ips: list[str], allow_ports: list[int], timeout: float = 180.0
    ) -> None:
        """Enforce the egress posture on ``name`` (deny by default; allowlist when given).

        The default runs the Linux ``nft`` lock-down script in the guest via
        :meth:`exec` and raises :class:`~lince_lab.errors.BackendError` on a
        nonzero exit. Backends whose guest is not Linux (e.g. macOS) override this
        with an OS-appropriate mechanism. This lives on the seam — not in the
        broker — so egress enforcement is per-backend, not Linux-assuming.
        """
        from lince_lab.errors import BackendError
        from lince_lab.templates import egress_lockdown_argv

        result = self.exec(name, egress_lockdown_argv(allow_ips, allow_ports), timeout=timeout)
        if result.exit_code != 0:
            raise BackendError(
                f"egress lock-down failed on {name} (exit {result.exit_code}): {result.stderr.strip() or 'no detail'}"
            )
