"""Broker server — the host-side mediator between agent and VM (blueprint §3).

:class:`BrokerServer` listens on an ``AF_UNIX`` ``SOCK_STREAM`` socket (mode
``0600``, owner-only), accepts one connection at a time, and for each request:

1. decodes + validates the envelope (a malformed line → ``DATA_ERROR`` / 65; an
   unknown verb → ``UNKNOWN_VERB`` / 64 — both surfaced as ``error.exit``);
2. runs :func:`lince_lab.policy.check` (the client-untrusted gate; a violation →
   ``POLICY_DENIED`` / 13);
3. dispatches the policy-cleaned args to the injected :class:`Backend`
   (``vm.*`` / ``snap.*``), to :mod:`lince_lab.recipe` (``recipe.validate`` /
   ``recipe.run``), to :mod:`lince_lab.bisect` (``bisect.run``), or upgrades the
   connection to a line stream for ``capture.*``;
4. writes one response envelope, carrying ``error.exit`` on failure.

The server is single-threaded but guards each VM with a per-VM lock so a future
threaded accept loop serializes operations on the same instance. It is
constructed with an injected :class:`Backend` — ``FakeBackend`` in tests,
``LimaBackend`` in production — so the whole dispatch path is exercisable over a
real unix socket with no VM.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable

from lince_lab import protocol
from lince_lab.backend import Backend, ExecResult, VmState
from lince_lab.capture import Capture
from lince_lab.config import apply_preset
from lince_lab.errors import DataError, LabError
from lince_lab.paths import VM_NAME_PREFIX, parse_size
from lince_lab.policy import artifacts_root
from lince_lab.policy import check as policy_check
from lince_lab.policy import check_capture as policy_check_capture
from lince_lab.recipe import Recipe, effective_egress, load_recipe, run_recipe, validate
from lince_lab.templates import build_template


class BrokerServer:
    """A single-threaded unix-socket broker over an injected :class:`Backend`."""

    def __init__(
        self,
        socket_path: str | Path,
        backend: Backend,
        config: dict[str, Any] | None = None,
        *,
        home: Path | None = None,
    ) -> None:
        self.socket_path = str(socket_path)
        self.backend = backend
        self.config = dict(config or {})
        self.home = home
        self._sock: socket.socket | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._stop = threading.Event()
        self._dispatch: dict[str, Callable[[dict[str, Any]], Any]] = self._build_dispatch()

    # Cap on the per-VM lock table so a long-lived broker churning many VM names
    # cannot grow it without bound (see :meth:`_lock_for`).
    _MAX_LOCKS = 256

    # ── server lifecycle ─────────────────────────────────────────────────────
    def bind(self) -> None:
        """Create the listening socket at ``socket_path`` with mode ``0600``."""
        sock_path = Path(self.socket_path)
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        if sock_path.exists():
            sock_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        sock.listen(8)
        self._sock = sock

    def serve_forever(self) -> None:
        """Accept and handle connections until :meth:`stop` is called."""
        if self._sock is None:
            self.bind()
        assert self._sock is not None
        self._sock.settimeout(0.25)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    self.handle_connection(conn)
                except OSError:
                    pass

    def stop(self) -> None:
        """Signal the accept loop to exit and close the listening socket."""
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        # Best-effort unlink so a restart can rebind cleanly.
        try:
            Path(self.socket_path).unlink()
        except FileNotFoundError:
            pass

    # ── per-connection handling ──────────────────────────────────────────────
    def handle_connection(self, conn: socket.socket) -> None:
        """Serve newline-JSON requests on ``conn`` until the peer closes it."""
        rbuf = bytearray()
        while True:
            line = protocol.read_line(conn.recv, rbuf)
            if line is None:
                return
            response, capture_setup = self._handle_line(line)
            conn.sendall(protocol.encode(response))
            if capture_setup is not None:
                # capture.open succeeded: upgrade this connection to a line stream.
                self._run_capture_stream(conn, rbuf, capture_setup)
                return

    def _handle_line(self, line: bytes) -> tuple[dict[str, Any], "_CaptureSetup | None"]:
        """Decode + dispatch one request line; return ``(response, capture_setup)``.

        ``capture_setup`` is non-``None`` only for a successful ``capture.open``,
        signaling the caller to upgrade the connection to a capture line stream.
        """
        request_id = "unknown"
        try:
            envelope = protocol.decode(line)
            request_id, verb, args = protocol.validate_request(envelope)
            return self._dispatch_request(request_id, verb, args)
        except LabError as exc:
            code = type(exc).__name__
            return protocol.make_error(request_id, code, str(exc), exc.exit_code), None
        except Exception as exc:  # noqa: BLE001 - last-resort guard; never leak a stack
            return (
                protocol.make_error(request_id, "INTERNAL", f"broker internal error: {exc}", 1),
                None,
            )

    # Verbs that take a recipe path and run an orchestration over a loaded recipe.
    _RECIPE_VERBS: frozenset[str] = frozenset({"recipe.validate", "recipe.run", "bisect.run"})

    def _dispatch_request(
        self, request_id: str, verb: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], "_CaptureSetup | None"]:
        """Policy-check then route a validated request to its handler.

        For orchestration verbs the recipe TOML is loaded **once** here, used both
        to derive the trusted policy context and passed to the handler, so the file
        is never parsed twice per request.
        """
        recipe = self._load_recipe_for(verb, args)
        recipe_ctx = self._recipe_ctx(recipe)
        safe_args = policy_check(verb, args, recipe_ctx, home=self.home)

        if verb == "capture.open":
            setup = self._open_capture(safe_args)
            return protocol.make_ok(request_id, {"opened": True}), setup

        if recipe is not None:
            result = self._run_recipe_handler(verb, recipe, safe_args)
            return protocol.make_ok(request_id, result), None

        handler = self._dispatch.get(verb)
        if handler is None:
            # capture.send / capture.snapshot off-stream, or an unrouted verb.
            raise DataError(f"verb {verb!r} is not valid outside a capture stream")

        vm_name = args.get("name")
        if isinstance(vm_name, str) and vm_name:
            with self._lock_for(vm_name):
                result = handler(safe_args)
        else:
            result = handler(safe_args)
        return protocol.make_ok(request_id, result), None

    # ── recipe loading + context (server-side trusted facts for policy) ──────
    def _load_recipe_for(self, verb: str, args: dict[str, Any]) -> Recipe | None:
        """Load the recipe for an orchestration ``verb`` once (else ``None``).

        A non-recipe verb yields ``None``. A recipe verb missing its ``recipe``
        path, or whose TOML fails to load, raises ``DATA_ERROR`` (exit 65) — the
        client gets a clear data error rather than a confusing fall-through.
        """
        if verb not in self._RECIPE_VERBS:
            return None
        recipe_path = args.get("recipe")
        if not isinstance(recipe_path, str) or not recipe_path:
            raise DataError(f"{verb} requires a 'recipe' path")
        return load_recipe(recipe_path)

    def _recipe_ctx(self, recipe: Recipe | None) -> dict[str, Any]:
        """Build the trusted recipe context the policy check needs from a recipe.

        Exposes the recipe's resolved workspace dir + network posture. A **bare**
        ``vm.copy_in`` over the wire carries *no* server-side recipe context — the
        recipe run flow stages the workspace via ``backend.copy_in`` directly,
        never through this verb — so the broker supplies an empty context and
        policy fail-closes (a client ``workspace_dir`` is never trusted, §3.3).
        """
        if recipe is None:
            return {}
        workspace = recipe.workspace.get("host_dir")
        workspace_dir = str((recipe.source_dir / str(workspace)).resolve()) if workspace else None
        return {"workspace_dir": workspace_dir, "network": recipe.network}

    def _run_recipe_handler(self, verb: str, recipe: Recipe, args: dict[str, Any]) -> dict[str, Any]:
        """Route an orchestration verb to its handler with the pre-loaded recipe."""
        if verb == "recipe.validate":
            return self._h_recipe_validate(recipe)
        if verb == "recipe.run":
            return self._h_recipe_run(recipe, args)
        return self._h_bisect_run(recipe, args)

    def _lock_for(self, vm_name: str) -> threading.Lock:
        """Return the per-VM lock, capping the lock table so it cannot grow without bound.

        A future threaded accept loop serializes operations on the same instance
        via this lock. The table is bounded: once it reaches ``_MAX_LOCKS`` an
        unheld lock is evicted to make room (a held one is never evicted), so a long
        broker uptime churning many VM names cannot leak unbounded locks.
        """
        lock = self._locks.get(vm_name)
        if lock is not None:
            return lock
        if len(self._locks) >= self._MAX_LOCKS:
            for name, existing in list(self._locks.items()):
                if existing.acquire(blocking=False):
                    existing.release()
                    del self._locks[name]
                    break
        lock = threading.Lock()
        self._locks[vm_name] = lock
        return lock

    # ── verb routing table ───────────────────────────────────────────────────
    def _build_dispatch(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "ping": self._h_ping,
            "vm.create": self._h_create,
            "vm.start": self._h_start,
            "vm.stop": self._h_stop,
            "vm.delete": self._h_delete,
            "vm.status": self._h_status,
            "vm.list": self._h_list,
            "vm.exec": self._h_exec,
            "vm.copy_in": self._h_copy_in,
            "vm.copy_out": self._h_copy_out,
            "snap.create": self._h_snap_create,
            "snap.apply": self._h_snap_apply,
            "snap.delete": self._h_snap_delete,
            "snap.list": self._h_snap_list,
        }

    # ── liveness ─────────────────────────────────────────────────────────────
    def _h_ping(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"pong": True, "v": protocol.PROTOCOL_VERSION}

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _h_create(self, args: dict[str, Any]) -> dict[str, Any]:
        # Template is forced server-side and the client's template is ignored
        # ENTIRELY (policy already strips ``template_yaml``; we never read it). The
        # broker rebuilds the policy-forced template from its own config + the
        # request's declared sizing needs. A bare ``vm up`` declares no image, so
        # we fall back to the config's ``default_image`` — a real Lima backend
        # rejects an empty template ("got empty instConfig"), so a bootable image
        # is always resolved.
        needs = {
            "image": args.get("image") or self.config.get("default_image", "fedora"),
            "cpus": args.get("cpus"),
            "memory": args.get("memory"),
            "disk": args.get("disk"),
        }
        template = build_template(self.config, needs)
        self.backend.create(args["name"], template)
        return {"created": args["name"]}

    def _h_start(self, args: dict[str, Any]) -> dict[str, Any]:
        # A bare `vm up` (vm.start verb) boots a networked VM, then is locked down
        # DENY-by-default: only loopback + established/related (Lima SSH) survive,
        # no agent-initiated egress. This is the server-applied, never
        # client-chosen, deny posture an interactive `vm up` gets — so oracle 01's
        # network-off probe passes. run_recipe / _build_base_vm call
        # backend.start() DIRECTLY (not this verb), so their provisioning keeps
        # network up and they apply their own (recipe-posture) lock-down after
        # provisioning — they are unaffected by this deny default.
        self.backend.start(args["name"])
        # Apply the server-side deny-by-default egress posture. The backend picks
        # the OS-appropriate mechanism (Linux nft for Lima; macOS backends override),
        # capped so it errors out instead of hanging forever.
        self.backend.apply_egress_lockdown(args["name"], [], [], timeout=180.0)
        return {"started": args["name"]}

    def _h_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.stop(args["name"], force=bool(args.get("force", False)))
        return {"stopped": args["name"]}

    def _h_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.delete(args["name"], force=bool(args.get("force", False)))
        return {"deleted": args["name"]}

    def _h_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return _vmstate_to_dict(self.backend.status(args["name"]))

    def _h_list(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        # Disclose ONLY lab-namespaced instances; a user's other VMs (which a real
        # `limactl list` would include) are never surfaced over the broker.
        return [_vmstate_to_dict(s) for s in self.backend.list() if s.name.startswith(VM_NAME_PREFIX)]

    # ── exec / files ─────────────────────────────────────────────────────────
    def _h_exec(self, args: dict[str, Any]) -> dict[str, Any]:
        argv = [str(a) for a in (args.get("argv") or [])]
        env = args.get("env") if isinstance(args.get("env"), dict) else None
        result: ExecResult = self.backend.exec(
            args["name"],
            argv,
            workdir=args.get("workdir"),
            env=env,
            timeout=args.get("timeout"),
        )
        return {"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr}

    def _h_copy_in(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.copy_in(
            args["name"],
            str(args["host_path"]),
            str(args["guest_path"]),
            recursive=bool(args.get("recursive", False)),
        )
        return {"copied_in": args["guest_path"]}

    def _h_copy_out(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.copy_out(
            args["name"],
            str(args["guest_path"]),
            str(args["host_path"]),
            recursive=bool(args.get("recursive", False)),
        )
        return {"copied_out": args["host_path"]}

    # ── snapshots ────────────────────────────────────────────────────────────
    def _h_snap_create(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.snapshot_create(args["name"], str(args["tag"]))
        return {"snapshot": args["tag"]}

    def _h_snap_apply(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.snapshot_apply(args["name"], str(args["tag"]))
        return {"applied": args["tag"]}

    def _h_snap_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        self.backend.snapshot_delete(args["name"], str(args["tag"]))
        return {"deleted": args["tag"]}

    def _h_snap_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"snapshots": self.backend.snapshot_list(args["name"])}

    # ── recipe / bisect ──────────────────────────────────────────────────────
    # These handlers receive the Recipe already loaded once by _dispatch_request,
    # so the TOML is never parsed twice per orchestration request.
    def _h_recipe_validate(self, recipe: Recipe) -> dict[str, Any]:
        validate(recipe, self.config or None)
        return {"valid": True, "recipe": recipe.name}

    def _h_recipe_run(self, recipe: Recipe, args: dict[str, Any]) -> dict[str, Any]:
        # Record the effective egress decision (deny, or the resolved allow rules)
        # to <artifacts>/egress.log BEFORE running, so the log reflects the posture
        # the run is about to enforce even if a step later fails (blueprint §3.2).
        config = self._effective_config(args)
        egress_log = self._write_egress_log(recipe)
        exit_code = run_recipe(self.backend, recipe, config, keep=self._effective_keep(config, args))
        return {"exit_code": exit_code, "recipe": recipe.name, "egress_log": str(egress_log)}

    def _effective_config(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the run config with the request's named ``preset`` overlaid.

        A ``--preset`` carried on the request overlays the broker's base config so
        the preset's resource / lifecycle knobs (cpus / memory / disk, keep_vm,
        step_timeout_s, retain_base_snapshot) take effect for this run. An unknown
        preset is a client data error (exit 65).
        """
        preset = args.get("preset")
        if not preset:
            return self.config
        try:
            return apply_preset(self.config, str(preset))
        except KeyError as exc:
            raise DataError(f"unknown preset {preset!r}") from exc

    @staticmethod
    def _effective_keep(config: dict[str, Any], args: dict[str, Any]) -> bool:
        """Resolve whether to keep the VM: explicit client ``keep`` wins, else the preset's ``keep_vm``."""
        if "keep" in args:
            return bool(args["keep"])
        return bool(config.get("keep_vm", False))

    def _write_egress_log(self, recipe: Recipe) -> Path:
        """Write the effective egress decision to ``<artifacts>/egress.log``.

        The artifacts root is server-derived (:func:`policy.artifacts_root`) under
        the broker's home — never a client value. The decision is the same one
        :func:`build_template` bakes into the boot script, so the log is an honest
        record of the posture the VM will run under. Returns the log path.
        """
        home = self.home if self.home is not None else Path.home()
        out_root = artifacts_root(home)
        out_root.mkdir(parents=True, exist_ok=True)
        decision = effective_egress(recipe)
        document = {"recipe": recipe.name, "egress": decision}
        log_path = out_root / "egress.log"
        log_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return log_path

    def _h_bisect_run(self, recipe: Recipe, args: dict[str, Any]) -> dict[str, Any]:
        from lince_lab.bisect import run_bisect

        document = run_bisect(
            self.backend,
            recipe,
            self.config,
            good=str(args["good"]),
            bad=str(args["bad"]),
            repo_dir=str(args["repo_dir"]),
            out_path=str(args.get("out", "bisect.json")),
            keep=bool(args.get("keep", False)),
        )
        return document

    # ── capture stream ───────────────────────────────────────────────────────
    def _open_capture(self, args: dict[str, Any]) -> "_CaptureSetup":
        program = [str(a) for a in (args.get("program") or [])]
        cols, rows = parse_size(str(args.get("size", "80x24")))
        channel = self.backend.open_capture(args["name"], program, cols, rows)
        return _CaptureSetup(Capture(channel, cols, rows))

    def _run_capture_stream(self, conn: socket.socket, rbuf: bytearray, setup: "_CaptureSetup") -> None:
        """Serve ``capture.send`` / ``capture.snapshot`` over the upgraded stream.

        Each subsequent request on this connection drives the open
        :class:`Capture`; the response (or a snapshot/wait grid) is written back
        as a normal envelope. The stream ends when the peer closes the connection
        or sends ``capture.close``.
        """
        capture = setup.capture
        try:
            while True:
                line = protocol.read_line(conn.recv, rbuf)
                if line is None:
                    return
                request_id = "unknown"
                try:
                    envelope = protocol.decode(line)
                    request_id, verb, args = protocol.validate_request(envelope)
                    # Gate every capture-stream verb through policy before it can
                    # drive the live channel — the upgraded stream is NOT a policy
                    # bypass (blueprint §3).
                    safe_args = policy_check_capture(verb, args, home=self.home)
                    result = self._handle_capture_verb(capture, verb, safe_args)
                    conn.sendall(protocol.encode(protocol.make_ok(request_id, result)))
                except LabError as exc:
                    conn.sendall(
                        protocol.encode(protocol.make_error(request_id, type(exc).__name__, str(exc), exc.exit_code))
                    )
                except Exception as exc:  # noqa: BLE001
                    conn.sendall(
                        protocol.encode(protocol.make_error(request_id, "INTERNAL", f"capture error: {exc}", 1))
                    )
        finally:
            capture.close()

    @staticmethod
    def _handle_capture_verb(capture: Capture, verb: str, args: dict[str, Any]) -> Any:
        """Route one in-stream capture request to the :class:`Capture` instance."""
        if verb == "capture.send":
            keys = args.get("keys")
            if keys is not None:
                capture.send_keys([str(k) for k in keys])
            elif "payload" in args:
                capture.input(str(args["payload"]))
            elif "wait_for" in args:
                grid = capture.wait_for_substring(str(args["wait_for"]), timeout_s=float(args.get("timeout_s", 60)))
                return _grid_to_dict(grid)
            elif "stable_ms" in args:
                grid = capture.wait_for_stable(int(args["stable_ms"]), timeout_s=float(args.get("timeout_s", 60)))
                return _grid_to_dict(grid)
            return {"sent": True}
        if verb == "capture.snapshot":
            grid = capture.snapshot(timeout_s=float(args.get("timeout_s", 5)))
            return _grid_to_dict(grid)
        raise DataError(f"verb {verb!r} is not a capture-stream verb")


class _CaptureSetup:
    """Carries the open :class:`Capture` from ``capture.open`` to the stream loop."""

    def __init__(self, capture: Capture) -> None:
        self.capture = capture


# ── module-level helpers ─────────────────────────────────────────────────────


def _vmstate_to_dict(state: VmState) -> dict[str, Any]:
    """Serialize a :class:`VmState` for the wire."""
    return {"name": state.name, "status": state.status.value, "snapshots": list(state.snapshots)}


def _grid_to_dict(grid: Any) -> dict[str, Any]:
    """Serialize a :class:`~lince_lab.capture.Grid` for the wire."""
    return {"cols": grid.cols, "rows": grid.rows, "text": grid.text}
