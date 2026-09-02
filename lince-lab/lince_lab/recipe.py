"""Recipe schema, validation, and run-flow orchestration (blueprint §5).

A *recipe* is a TOML file describing a disposable-VM test: which image to boot,
what network posture to allow, the one host workspace to stage, the provision
scripts baked into a base snapshot, the ordered steps to drive (plain ``exec``
steps and ``ht``-driven ``capture`` steps), and the mandatory ``[assert]`` block
that decides pass/fail.

This module is pure logic over the :class:`~lince_lab.backend.Backend` seam, so
the whole validate + run flow is exercisable against ``FakeBackend`` with no VM.

Three public entry points:

* :func:`load_recipe` — parse a TOML file into a :class:`Recipe` (records the
  recipe's source directory so ``[workspace].host_dir`` can be path-bounded).
* :func:`validate` — enforce the schema invariants, raising
  :class:`~lince_lab.errors.DataError` (exit 65) on any violation.
* :func:`run_recipe` — execute the section-5 flow and return the result exit
  code (0 if every assertion passes, else the failing code).
"""

from __future__ import annotations

import shlex
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lince_lab.backend import Backend
from lince_lab.capture import Capture, Grid
from lince_lab.errors import BackendError, DataError
from lince_lab.paths import parse_size, resolves_under, slug_vm_name
from lince_lab.templates import build_template, resolve_allow_ips, resolve_allow_map

# Snapshot tag baked after provisioning so retries / bisect can reset cheaply.
BASE_SNAPSHOT_TAG = "base-clean"


@dataclass
class Recipe:
    """A parsed recipe.

    ``source_dir`` is the directory the recipe TOML lives in; relative paths in
    the recipe (notably ``[workspace].host_dir``) resolve under it and must not
    escape it. The remaining fields mirror the TOML tables verbatim so the run
    flow and validation read them directly.
    """

    name: str
    description: str
    version: str
    vm: dict[str, Any]
    network: dict[str, Any]
    workspace: dict[str, Any]
    assertions: dict[str, Any]
    provision: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    sync: dict[str, Any] = field(default_factory=dict)
    source_dir: Path = field(default_factory=Path.cwd)

    def has_capture_step(self) -> bool:
        """Return ``True`` iff any step drives a terminal via ``capture``."""
        return any(bool(step.get("capture")) for step in self.steps)


def load_recipe(path: str | Path) -> Recipe:
    """Parse the recipe TOML at ``path`` into a :class:`Recipe`.

    Records ``source_dir`` = the recipe file's parent so ``[workspace].host_dir``
    can be resolved and path-bounded during :func:`validate`. A malformed TOML
    file raises :class:`~lince_lab.errors.DataError` (exit 65).
    """
    recipe_path = Path(path).expanduser()
    try:
        raw = recipe_path.read_bytes()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError) as exc:
        raise DataError(f"cannot read recipe {recipe_path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise DataError(f"malformed recipe TOML {recipe_path}: {exc}") from exc

    recipe_block = data.get("recipe") or {}
    return Recipe(
        name=str(recipe_block.get("name", "")),
        description=str(recipe_block.get("description", "")),
        version=str(recipe_block.get("version", "")),
        vm=dict(data.get("vm") or {}),
        network=dict(data.get("network") or {}),
        workspace=dict(data.get("workspace") or {}),
        assertions=dict(data.get("assert") or {}),
        provision=list(data.get("provision") or []),
        steps=list(data.get("step") or []),
        sync=dict(data.get("sync") or {}),
        source_dir=recipe_path.resolve().parent,
    )


# ── assertion keys that count toward "≥1 assertion present" ──────────────────
_ASSERTION_KEYS = ("exit_code", "grid_contains", "grid_absent", "file_exists")


def validate(recipe: Recipe, config: dict[str, Any] | None = None) -> None:
    """Validate ``recipe`` against the schema; raise on any violation.

    Raises :class:`~lince_lab.errors.DataError` (exit 65) on:

    * a missing ``[recipe]`` / ``[vm]`` / ``[workspace]`` / ``[assert]`` table;
    * an ``[assert]`` table containing zero assertions;
    * any ``capture`` step lacking a ``[sync]`` section;
    * ``[network] mode = "allow"`` with an empty allowlist;
    * a ``[workspace].host_dir`` that does not resolve under the recipe dir;
    * an image not present in ``config``'s allowed image set (when ``config`` is
      supplied — image-allowlist validation is skipped if no config is given).
    """
    # ── required tables ──
    if not recipe.name:
        raise DataError("recipe is missing a [recipe] table with a name")
    if not recipe.vm:
        raise DataError("recipe is missing the required [vm] table")
    if not recipe.workspace:
        raise DataError("recipe is missing the required [workspace] table")
    if not recipe.assertions:
        raise DataError("recipe is missing the required [assert] table")

    # ── at least one assertion ──
    if not any(key in recipe.assertions for key in _ASSERTION_KEYS):
        raise DataError(f"[assert] must contain at least one assertion (one of: {', '.join(_ASSERTION_KEYS)})")

    # ── every capture step needs [sync] ──
    if recipe.has_capture_step() and not recipe.sync:
        raise DataError("a capture step requires a [sync] section, but none is present")

    # ── network allow requires a non-empty allowlist (structural check) ──
    # This is a pure schema invariant: an ``allow`` posture must declare at least
    # one host or port. DNS resolution of those hosts to concrete IPs is a
    # *run-time* concern done host-side in :func:`recipe_needs` /
    # :func:`effective_egress` / :func:`build_template` — all of which fail closed
    # to a deny cut when zero hosts resolve. Keeping resolution out of validate()
    # makes validation pure and offline-safe (no network dependency), so a
    # substrate-free `run validate` is deterministic on a hermetic CI host.
    if recipe.network.get("mode") == "allow":
        allow_hosts = recipe.network.get("allow_hosts") or []
        allow_ports = recipe.network.get("allow_ports") or []
        if not allow_hosts and not allow_ports:
            raise DataError("[network] mode = 'allow' requires a non-empty allow_hosts/allow_ports allowlist")

    # ── workspace host_dir must resolve under the recipe dir ──
    host_dir = recipe.workspace.get("host_dir")
    if not host_dir:
        raise DataError("[workspace] is missing a host_dir")
    if not resolves_under(recipe.source_dir, str(host_dir)):
        raise DataError(
            f"[workspace] host_dir {host_dir!r} does not resolve under the recipe directory {recipe.source_dir}"
        )

    # ── image must be in the config allowlist (when a config is provided) ──
    if config is not None:
        image_name = recipe.vm.get("image")
        if not image_name:
            raise DataError("[vm] is missing an image")
        images = config.get("images") or {}
        if image_name not in images:
            known = ", ".join(sorted(images)) or "(none)"
            raise DataError(f"image {image_name!r} is not in the config allowlist; allowed: {known}")


# ── run flow (blueprint §5) ──────────────────────────────────────────────────


def run_recipe(
    backend: Backend,
    recipe: Recipe,
    config: dict[str, Any],
    keep: bool = False,
) -> int:
    """Execute ``recipe`` against ``backend`` and return the result exit code.

    The section-5 flow:

    1. :func:`validate` (fail-fast).
    2. Build the policy-forced template (no egress boot provision — the VM boots
       networked), ``create`` + ``start`` the VM.
    3. Run ``[[provision]]`` with the network UP (trusted toolchain setup), THEN
       apply the runtime egress lock-down (:func:`apply_egress_lockdown`) — a
       nonzero lock-down exit fails the run — THEN
       ``snapshot_create(BASE_SNAPSHOT_TAG)`` so every reset candidate is already
       restricted.
    4. ``copy_in`` the workspace ``host_dir`` → ``guest_dir`` (policy-bounded).
    5. For each ``[[step]]`` (now running under the egress lock-down): a
       ``capture`` step opens a channel and, for each key batch, waits for the
       configured substring, waits for the grid to settle, then ``send_keys``; an
       ``exec`` step runs its argv capturing the exit code.
    6. Evaluate ``[assert]`` (exit_code match; ``grid_contains`` / ``grid_absent``
       against the final settled grid; ``file_exists`` via ``test -f``).
    7. Return 0 if every assertion passes, else the failing exit code. The VM is
       deleted unless ``keep`` is set; the base snapshot is dropped after staging
       unless the effective config's ``retain_base_snapshot`` knob is set (the
       ``bisect`` preset retains it for fast per-candidate reset).

    The effective ``config`` is consulted for two preset-tunable knobs:
    ``step_timeout_s`` (the per-exec-step timeout) and ``retain_base_snapshot``.

    Returns the recipe exit code:

    * the last step's nonzero exit code if a step fails, otherwise
    * 0 if all assertions pass, otherwise
    * 65 (``DATA_ERROR``) for an assertion mismatch (grid / file / exit_code).
    """
    validate(recipe, config)

    vm_name = _vm_name(recipe)
    needs = recipe_needs(recipe)
    template_yaml = build_template(config, needs)
    step_timeout = step_timeout_of(config)
    retain_base = bool(config.get("retain_base_snapshot", False))

    backend.create(vm_name, template_yaml)
    backend.start(vm_name)
    try:
        # 3. provision (network UP — trusted setup) → egress lock-down → snapshot.
        # The template boots networked so provisioning can install tooling
        # (ht / node / git / ...); the egress lock-down is applied AFTER provision
        # and BEFORE the snapshot so every reset candidate runs restricted, and
        # BEFORE the (untrusted) recipe steps. A lock-down failure fails the run.
        provisions = [e for e in recipe.provision if e.get("script")]
        for i, entry in enumerate(provisions, 1):
            # Provision output is captured (not streamed), so a slow step (e.g.
            # `dnf install nodejs npm`) is an otherwise-silent multi-minute wait.
            # Announce it so the run does not look hung.
            print(
                f"lince-lab: provisioning VM {vm_name!r} (step {i}/{len(provisions)}; "
                "installing the toolchain — this can take a few minutes, output is captured)…",
                file=sys.stderr,
                flush=True,
            )
            backend.exec(vm_name, ["sh", "-c", str(entry["script"])], timeout=step_timeout)
        if provisions:
            print(f"lince-lab: provisioning complete on {vm_name!r}", file=sys.stderr, flush=True)
        print("lince-lab: applying egress lock-down…", file=sys.stderr, flush=True)
        apply_egress_lockdown(backend, vm_name, recipe, step_timeout=step_timeout)
        backend.snapshot_create(vm_name, BASE_SNAPSHOT_TAG)

        # 4. stage the single workspace dir (policy-bounded host_dir).
        print("lince-lab: staging workspace…", file=sys.stderr, flush=True)
        host_dir = str(recipe.workspace["host_dir"])
        guest_dir = str(recipe.workspace.get("guest_dir", "/work"))
        if not resolves_under(recipe.source_dir, host_dir):
            raise DataError(f"workspace host_dir {host_dir!r} escapes the recipe directory; refusing copy_in")
        # host_dir is recipe-RELATIVE (e.g. "./fixtures/npm-smoke", shipped beside
        # the recipe). Resolve it to an absolute path under the recipe dir so the
        # backend copies the right tree — limactl/rsync would otherwise resolve a
        # relative source against ITS own working directory, not the recipe's.
        # host_dir is recipe-RELATIVE; resolve it absolute under the recipe dir,
        # then stage its CONTENTS into guest_dir (see stage_workspace) so a recipe
        # step finds its files at <guest_dir>/<file> (e.g. /work/lince-config).
        abs_host_dir = str((recipe.source_dir / host_dir).resolve())
        prepare_guest_dir(backend, vm_name, guest_dir, step_timeout=step_timeout)
        stage_workspace(backend, vm_name, abs_host_dir, guest_dir, step_timeout=step_timeout)

        # A single run never resets, so the base snapshot is dead weight unless the
        # effective config asks to keep it; drop it to reclaim disk (consumes the
        # retain_base_snapshot preset knob). Best-effort: a backend that cannot
        # delete the snapshot must not fail an otherwise-good run.
        if not retain_base:
            try:
                backend.snapshot_delete(vm_name, BASE_SNAPSHOT_TAG)
            except BackendError:
                pass

        # 5-6. run the ordered steps + evaluate the assertions. Shared verbatim
        # with the bisect loop via run_steps_and_assert (single-sourced oracle).
        exit_code, _step_failed = run_steps_and_assert(backend, recipe, vm_name, step_timeout=step_timeout)
        return exit_code
    finally:
        if not keep:
            backend.delete(vm_name, force=True)


def stage_workspace(
    backend: Backend, vm_name: str, host_dir_abs: str, guest_dir: str, *, step_timeout: float | None = None
) -> None:
    """Copy ``host_dir_abs`` into the VM so its CONTENTS land at ``guest_dir``.

    ``limactl copy`` copies a directory INTO the destination
    (``<guest_dir>/<basename>/...``), so after the copy we move that basename
    subdir's contents up to ``guest_dir`` — recipes address staged files at
    ``<guest_dir>/<name>`` (e.g. ``/work/lince-config``), not under a subdir. The
    flatten is tolerant: if a backend instead placed the contents directly (no
    basename subdir), the move is a harmless no-op (``|| true``) and the workspace
    is already in place. ``cp -a`` preserves modes (``install.sh`` stays
    executable) and copies dotfiles via the trailing ``/.``.
    """
    base = Path(host_dir_abs).name
    backend.copy_in(vm_name, host_dir_abs, guest_dir, recursive=True)
    flatten = (
        f"cd {shlex.quote(guest_dir)} && [ -d {shlex.quote(base)} ] "
        f"&& cp -a {shlex.quote(base + '/.')} ./ && rm -rf {shlex.quote(base)} || true"
    )
    backend.exec(vm_name, ["sh", "-c", flatten], timeout=step_timeout)


def prepare_guest_dir(backend: Backend, vm_name: str, guest_dir: str, *, step_timeout: float | None = None) -> None:
    """Create ``guest_dir`` in the VM and chown it to the (non-root) guest user.

    A disposable Lima guest runs as a non-root user, so an unprivileged ``rsync``
    copy can neither create a dest like ``/work`` (``mkdir`` → Permission denied)
    nor set the group on a root-owned dest (``chgrp`` → Operation not permitted).
    We pre-create the dir with sudo and hand it to the guest user so the workspace
    copy — and the steps that write into it — succeed and rsync's
    group-preservation becomes a no-op.

    The user/group are looked up with simple single-word execs and the chown
    target is a single token, so nothing relies on a multi-word shell argument
    surviving the ``limactl shell`` transport. Best-effort: if the directory truly
    cannot be staged, the subsequent ``copy_in`` fails loudly anyway.
    """
    owner = backend.exec(vm_name, ["id", "-un"], timeout=step_timeout).stdout.strip()
    ogroup = backend.exec(vm_name, ["id", "-gn"], timeout=step_timeout).stdout.strip()
    backend.exec(vm_name, ["sudo", "mkdir", "-p", guest_dir], timeout=step_timeout)
    if owner and ogroup:
        backend.exec(vm_name, ["sudo", "chown", f"{owner}:{ogroup}", guest_dir], timeout=step_timeout)


def step_timeout_of(config: dict[str, Any]) -> float | None:
    """Return the per-exec-step timeout (seconds) from the effective config, if any.

    ``step_timeout_s`` is a preset knob (e.g. the ``bisect`` preset's 600s); absent
    it is ``None`` (no timeout). Consumed by the exec-step runner here and by the
    bisect verdict runner.
    """
    value = config.get("step_timeout_s")
    return float(value) if value is not None else None


def run_steps_and_assert(
    backend: Backend,
    recipe: Recipe,
    vm_name: str,
    *,
    step_timeout: float | None = None,
) -> tuple[int, str | None]:
    """Run a recipe's ordered steps then evaluate its ``[assert]`` block.

    This is steps 5-6 of :func:`run_recipe`, factored out so the bisect loop can
    reuse the exact same oracle against a persistent, snapshot-reset VM (without
    the create / provision / delete lifecycle). ``step_timeout`` (the effective
    config's ``step_timeout_s``) bounds each exec step. Returns
    ``(exit_code, step_failed)``:

    * a failing exec step short-circuits to ``(its_code, step_name)``;
    * otherwise the assertions are evaluated — an ``exit_code`` mismatch yields
      ``(65, None)``; a ``grid_contains`` / ``grid_absent`` / ``file_exists``
      mismatch raises :class:`~lince_lab.errors.DataError` (exit 65), which
      :func:`run_recipe` propagates and the bisect verdict runner turns into a
      "bad" verdict.

    The VM lifecycle (create / provision / snapshot / delete) is the caller's concern.
    """
    last_exit = 0
    final_grid: Grid | None = None
    for i, step in enumerate(recipe.steps, 1):
        # Step output is captured, so announce each step — a network-bound step
        # (e.g. `npm install`) is otherwise a silent wait that reads as a hang.
        print(
            f"lince-lab: running step {i}/{len(recipe.steps)}: {step.get('name', '?')!r}…",
            file=sys.stderr,
            flush=True,
        )
        if step.get("capture"):
            final_grid = _run_capture_step(backend, vm_name, recipe, step)
        else:
            last_exit = _run_exec_step(backend, vm_name, step, step_timeout=step_timeout)
            if last_exit != 0:
                # A failing step is the oracle/bisect signal — stop and report.
                return last_exit, str(step.get("name", "?"))
    return _evaluate_assertions(backend, vm_name, recipe, last_exit, final_grid), None


def _vm_name(recipe: Recipe) -> str:
    """Build the policy-prefixed VM name for ``recipe`` (``lince-lab-<recipe>``)."""
    return slug_vm_name(recipe.name)


def recipe_needs(recipe: Recipe) -> dict[str, Any]:
    """Project a recipe into the ``recipe_needs`` dict :func:`build_template` wants.

    Only the boot-template inputs (image + resources + provision scripts) — egress
    is NOT baked into the template; it is resolved and enforced at runtime by
    :func:`apply_egress_lockdown`, so ``allow_hosts`` are deliberately not resolved
    here.
    """
    return {
        "image": recipe.vm.get("image"),
        "cpus": recipe.vm.get("cpus"),
        "memory": recipe.vm.get("memory"),
        "disk": recipe.vm.get("disk"),
        "provision": list(recipe.provision),
    }


def apply_egress_lockdown(
    backend: Backend,
    vm_name: str,
    recipe: Recipe,
    *,
    step_timeout: float | None = None,
) -> None:
    """Apply the runtime egress lock-down to a provisioned, network-up VM.

    Resolves the recipe's allow posture (``mode = "allow"`` → its ``allow_hosts``
    resolved to IPs host-side, fail-closed to deny when none resolve; else a
    drop-only deny), pins the resolved IPs into the guest ``/etc/hosts``, and
    applies the lock-down via ``backend.apply_egress_lockdown(...)`` while the
    network is still up. That seam runs the Linux nft script on the Lima backend;
    the macOS backend overrides it (pfctl enforcement is tracked for #266). A
    nonzero result raises :class:`~lince_lab.errors.BackendError`: a VM that cannot
    enforce egress must NOT go on to run the (now-untrusted) recipe steps.
    """
    # Cap the lock-down exec so a wedged script errors out instead of hanging
    # forever; honor a tighter step_timeout when the caller provides one.
    timeout = step_timeout if step_timeout is not None else 180.0

    # Resolve the allow map ONCE and derive both the nft IPs and the guest
    # /etc/hosts pin from it, so the two are consistent (the guest never connects
    # to an IP the nft rules did not allow). Fail-closed: if no host resolves, the
    # map is empty → no allow IPs → deny (drop-only), and no ports are opened.
    is_allow = recipe.network.get("mode") == "allow"
    host_ip_map = resolve_allow_map(list(recipe.network.get("allow_hosts") or [])) if is_allow else {}
    allow_ips = [ip for ips in host_ip_map.values() for ip in ips]
    allow_ports = [int(p) for p in (recipe.network.get("allow_ports") or [])] if (is_allow and allow_ips) else []

    # Pin the resolved IPs into the guest's /etc/hosts BEFORE the lock-down, so
    # the guest's name lookups resolve to exactly the allow-listed IPs without
    # needing DNS (DNS egress to the slirp resolver is dropped by the lock-down,
    # and a CDN's own DNS could otherwise return a different, non-allowed IP).
    if host_ip_map and allow_ips:
        _pin_guest_etc_hosts(backend, vm_name, host_ip_map, timeout=timeout)

    # Apply through the backend seam so a non-Linux guest (macOS) enforces egress
    # its own way instead of running the Linux nft script (which fail-closes on a
    # guest with no nft). Preserve the recipe-specific framing on failure.
    try:
        backend.apply_egress_lockdown(vm_name, allow_ips, allow_ports, timeout=timeout)
    except BackendError as exc:
        raise BackendError(f"{exc}; refusing to run steps unprotected") from exc


def _pin_guest_etc_hosts(
    backend: Backend,
    vm_name: str,
    host_ip_map: dict[str, list[str]],
    *,
    timeout: float | None = None,
) -> None:
    """Append ``<ip> <host>`` lines to the guest's ``/etc/hosts`` (sudo).

    Pins each allow_host to its FIRST host-resolved IP — which is also an
    nft-allowed IP — so the guest connects to exactly that destination without a
    DNS round-trip. The here-doc body is a single quoted ``sh -c`` argument (which
    survives the single-``--`` ``limactl shell`` transport, as provisioning shows).
    """
    lines = [f"{ips[0]} {host}" for host, ips in host_ip_map.items() if ips]
    if not lines:
        return
    body = "\n".join(lines)
    script = f"printf '%s\\n' {shlex.quote(body)} | sudo tee -a /etc/hosts >/dev/null"
    backend.exec(vm_name, ["sh", "-c", script], timeout=timeout)


def effective_egress(recipe: Recipe) -> dict[str, Any]:
    """Resolve the *effective* egress decision the run will enforce (blueprint §3.2).

    This mirrors exactly what :func:`build_template` bakes into the boot script,
    so the broker can record the decision it is about to enforce:

    * ``mode = "deny"`` → ``{"decision": "deny", "rules": []}`` (default-DROP cut).
    * ``mode = "allow"`` → the declared hosts are resolved **host-side** to IPs
      (fail-closed: a host that does not resolve is dropped, never widened) and
      paired with every allow port into ``ip daddr <ip> tcp dport <port> accept``
      rules. If *zero* hosts resolve the posture fails closed to ``"deny"`` — the
      same fallback :func:`build_template` performs — so the log never claims an
      allow posture that the VM will not actually have.

    The returned dict is JSON-serializable and is what the broker writes to
    ``egress.log``.
    """
    mode = str(recipe.network.get("mode", "deny"))
    if mode != "allow":
        return {"mode": mode, "decision": "deny", "rules": []}

    allow_hosts = list(recipe.network.get("allow_hosts") or [])
    allow_ports = [int(p) for p in (recipe.network.get("allow_ports") or [])] or [443]
    allow_ips = resolve_allow_ips(allow_hosts)
    if not allow_ips:
        # Fail-closed: an allow recipe whose hosts all failed DNS becomes a deny
        # cut (never any-host), matching build_template's fallback.
        return {
            "mode": mode,
            "decision": "deny",
            "rules": [],
            "allow_hosts": allow_hosts,
            "resolved_ips": [],
        }
    rules = [
        f"ip daddr {ip} tcp dport {port} accept" for ip in allow_ips for port in allow_ports
    ]
    return {
        "mode": mode,
        "decision": "allow",
        "allow_hosts": allow_hosts,
        "allow_ports": allow_ports,
        "resolved_ips": allow_ips,
        "rules": rules,
    }


def _run_exec_step(
    backend: Backend,
    vm_name: str,
    step: dict[str, Any],
    *,
    step_timeout: float | None = None,
) -> int:
    """Run a plain exec step's argv in the guest, returning its exit code.

    ``step_timeout`` (the effective config's ``step_timeout_s``) bounds the call.
    """
    run = step.get("run")
    if not run:
        raise DataError(f"exec step {step.get('name', '?')!r} is missing a 'run' argv")
    result = backend.exec(vm_name, [str(arg) for arg in run], timeout=step_timeout)
    return result.exit_code


def _run_capture_step(
    backend: Backend,
    vm_name: str,
    recipe: Recipe,
    step: dict[str, Any],
) -> Grid:
    """Drive a capture step via ``ht`` and return the final settled grid.

    For each key in ``step['keys']`` the runner first waits for the matching
    ``[sync].wait_for`` substring (when one is configured for that index), then
    waits for the grid to settle within ``[sync].stable_ms``, then injects the
    key. The grid after the last settle is returned for assertion evaluation.
    """
    program = step.get("program")
    if not program:
        raise DataError(f"capture step {step.get('name', '?')!r} is missing a 'program'")
    cols, rows = parse_size(str(step.get("size", "80x24")))

    sync = recipe.sync
    wait_for = list(sync.get("wait_for") or [])
    stable_ms = int(sync.get("stable_ms", 150))
    timeout_s = float(sync.get("timeout_s", 60))

    channel = backend.open_capture(vm_name, [str(arg) for arg in program], cols, rows)
    capture = Capture(channel, cols, rows)
    try:
        grid = capture.snapshot(timeout_s=timeout_s)
        for index, key in enumerate(step.get("keys") or []):
            if index < len(wait_for):
                grid = capture.wait_for_substring(str(wait_for[index]), timeout_s=timeout_s)
            grid = capture.wait_for_stable(stable_ms, timeout_s=timeout_s)
            capture.send_keys([str(key)])
        # Settle one final time so the grid reflects the last keypress's effect.
        grid = capture.wait_for_stable(stable_ms, timeout_s=timeout_s)
        return grid
    finally:
        capture.close()


def _evaluate_assertions(
    backend: Backend,
    vm_name: str,
    recipe: Recipe,
    last_exit: int,
    final_grid: Grid | None,
) -> int:
    """Evaluate ``[assert]`` and return 0 on pass or the failing exit code.

    A grid / file / exit_code mismatch is a data failure → exit 65. The
    ``exit_code`` assertion compares against the last exec step's code.
    """
    assertions = recipe.assertions

    if "exit_code" in assertions:
        expected = int(assertions["exit_code"])
        if last_exit != expected:
            # The recipe expected a specific code and the run produced another.
            return last_exit if last_exit != 0 else DataError.exit_code

    grid_text = final_grid.text if final_grid is not None else ""

    for needle in assertions.get("grid_contains") or []:
        if str(needle) not in grid_text:
            raise DataError(f"assertion failed: grid_contains {needle!r} not found on screen")

    for needle in assertions.get("grid_absent") or []:
        if str(needle) in grid_text:
            raise DataError(f"assertion failed: grid_absent {needle!r} appeared on screen")

    for path in assertions.get("file_exists") or []:
        result = backend.exec(vm_name, ["test", "-f", str(path)])
        if result.exit_code != 0:
            raise DataError(f"assertion failed: file_exists {path!r} not present in guest")

    return 0
