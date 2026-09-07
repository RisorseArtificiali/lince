---
name: lince-lab
description: Run and verify code in a disposable, isolated lab VM, and bisect regressions. Use when asked to test a fix in a clean machine, drive the lince quickstart wizard, check install.sh idempotency, reproduce a bug in isolation, or find which commit broke something. Authors a recipe TOML, runs it via the lince-lab CLI (broker over a unix socket), and reads the result artifacts — never runs limactl or touches the host filesystem directly.
license: MIT
compatibility: Requires the lince-lab CLI installed (lince-lab/install.sh) and a running broker (lince-lab lab broker start). Linux with /dev/kvm, limactl + qemu-img for real runs; LINCE_LAB_FAKE=1 for VM-free testing. Python 3.11+.
metadata:
  author: lince
  version: "1.0"
allowed-tools: Bash(lince-lab:*) Read(//home/**/.local/share/lince/lince-lab/**) Read(//home/**/.config/lince-lab/**) Write(//home/**/*.toml) Read(//home/**/bisect.json)
---

# lince-lab: Disposable Lab VMs + Autonomous Bisect (agent playbook)

Drive a throwaway VM to verify a fix, drive an interactive wizard, check
idempotency, or bisect a regression — **entirely through the `lince-lab` CLI**,
which speaks to a host-side broker over a unix socket. You never run `limactl`,
never touch the host filesystem, and never relax isolation: you declare intent in
a **recipe** and the broker decides what that intent is allowed to become.

## The loop you always follow

1. **Write a recipe** (`*.toml`) describing the test — image, network posture, the
   one host dir to stage, ordered steps, and a mandatory `[assert]`.
   ([references/recipes.md](references/recipes.md))
2. **Validate it**: `lince-lab run validate <recipe>` (exit 65 names any schema
   error — fix it before running).
3. **Run it**: `lince-lab run recipe <recipe>` — the CLI exits with the recipe's
   exit code (0 = pass).
4. **For a regression hunt**: `lince-lab find bisect <recipe> --good G --bad B
   --repo-dir D --out bisect.json`, then **read `bisect.json`** for `first_bad`.
   ([references/bisect.md](references/bisect.md))
5. **Read the artifacts** — the recipe exit code, the printed grid, `bisect.json` —
   to decide what to report.

## Hard rules

1. **CLI only.** Every action goes through `lince-lab`. NEVER run `limactl`,
   `qemu`, or shell into a VM directly. NEVER write into
   `~/.local/share/lince/lince-lab/` (shipped data, overwritten on update).
2. **Declare, don't inject.** Express needs in the recipe (`[vm]`, `[network]`,
   `[workspace]`). You cannot supply template YAML, mount host dirs, or open
   egress except through a recipe's explicit allowlist — the broker rebuilds the
   template server-side and will refuse anything else (policy denial → exit 13).
3. **One staged dir.** `[workspace].host_dir` must resolve **under the recipe
   file's directory**. Put fixtures next to the recipe; never point it at `~`,
   `~/.ssh`, or an absolute path outside the recipe dir.
4. **Network is deny-by-default.** Only set `[network] mode = "allow"` with a
   non-empty `allow_hosts`/`allow_ports` when the recipe genuinely fetches, and
   run it under the `networked` preset. ([references/presets.md](references/presets.md))
5. **No fixed sleeps for interactive steps.** Drive TUIs with capture steps +
   `[sync]` (`wait_for` / `stable_ms`), never by guessing timing.
   ([references/capture.md](references/capture.md))
6. **Always validate before run.** A failed `validate` (exit 65) tells you the
   exact key/table to fix; do not run an invalid recipe.

## Preconditions to check first — the broker is the operator's, not yours

You typically run **inside the agent-sandbox**, which by design has no `/dev/kvm`
and never owns `limactl`/QEMU. The broker is a **host-side process the human
operator starts**; you only ever talk to its unix socket. So the **first action of
any lince-lab session** is to confirm the broker is reachable — and if it is not,
**ask the operator to start it on the host**. Do not try to start it yourself from
the sandbox: it cannot work, and the failure looks like a missing `/dev/kvm`.

```bash
lince-lab lab doctor          # broker reachable? limactl present?
```

If the broker is unreachable, stop and ask the operator to run, **on the host (not
in the sandbox)**:

```bash
lince-lab lab broker start &  # host-side; add LINCE_LAB_FAKE=1 for a VM-free dry run
```

Only when you have confirmed you are running **directly on a KVM-capable host**
(not sandboxed) may you start the broker yourself. If `limactl` is missing or
`/dev/kvm` is absent on that host, report that it needs Lima + `qemu-img` +
`/dev/kvm` — do not try to work around it.

## Reading the result

| Surface | Read it for |
|---------|-------------|
| recipe exit code | 0 = all asserts passed; nonzero = the failing step/assert code |
| printed grid (capture steps / `watch grab`) | the terminal text the asserts checked |
| `bisect.json` | `first_bad`, `status` (`converged` / `no_regression` / `no_candidates`), per-candidate `verdicts` |

Report the outcome plainly: the recipe passed/failed, which assertion or step
failed, or the first-bad commit. Do not claim success without an exit code or
artifact backing it.

## Reference index

- **[references/recipes.md](references/recipes.md)** — recipe schema + how to write one.
- **[references/presets.md](references/presets.md)** — `quick` / `bisect` / `networked` and when to use each.
- **[references/bisect.md](references/bisect.md)** — the bisect loop and `bisect.json`.
- **[references/capture.md](references/capture.md)** — driving an interactive TUI deterministically.

Full design (ADR-01..ADR-10):
`docs/design/lince-lab-design.md`. User docs: `docs/documentation/lince-lab/`.
