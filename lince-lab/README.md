# lince-lab

Disposable lab-VM substrate for **autonomous testing and regression hunting**.

`lince-lab` gives an AI coding agent (or a human) a clean, throwaway virtual
machine it can provision, drive, snapshot, and assert against — without ever
exposing the host filesystem or host credentials to whatever runs inside.

## Why it exists — the sandbox blind spot

The `agent-sandbox` bubblewrap sandbox protects the **host** from the agent: it
confines what the agent process can read and write. But it does nothing to give
the agent a *safe place to run destructive or stateful experiments*. An agent
that wants to:

- run an `install.sh` twice to check it is idempotent,
- drive an interactive wizard (`lince-config quickstart`) to completion,
- `dnf install` / `npm install` real packages and observe the result, or
- **bisect** a regression by replaying a test across a range of commits,

has nowhere to do it. Doing any of that inside the agent's own sandbox mutates
the agent's environment, can't be reset cleanly, and risks the host when the
experiment needs root or real networking.

`lince-lab` fills that blind spot with a **disposable VM** the agent commands
through a narrow, policy-checked broker:

- The agent talks to a host-side **broker** over a unix socket — it never sees
  the VM's filesystem, only a closed set of verbs (create / exec / snapshot /
  capture / …).
- VMs are **isolated by construction**: no host mounts, no `~/.ssh` keys, no
  credential injection, deny-by-default networking, and a forced
  `lince-lab-*` name prefix so it can never touch your other VMs.
- Snapshots make per-experiment **reset** cheap, which is what makes the
  autonomous bisect loop possible.

The disposable VM is the experiment surface; the sandbox is the host guard. They
are complementary.

## Where it runs — host vs sandbox

The **broker runs on the host** (`lince-lab lab broker start`): it owns `limactl`,
QEMU and `/dev/kvm`, and is the only component that touches them. An agent — even
one inside the `agent-sandbox` — drives lince-lab purely through the broker's unix
socket (exposed read-write into the sandbox, existence-guarded). **The sandbox is
never granted `/dev/kvm`**: doing so would let an agent boot a VM with arbitrary
config (e.g. a host bind-mount = escape) and bypass the policy gate, so it is
deliberately avoided. Run the broker on a host with hardware virtualization (KVM);
v1 is Linux-only (a macOS backend is planned, #268).

## Install

```bash
bash lince-lab/install.sh     # installs the CLI, package, recipes, templates, skill
lince-lab --help
```

`install.sh` (idempotent, safe to re-run) places:

| What | Where |
|---|---|
| CLI executable | `~/.local/bin/lince-lab` |
| Python package + `recipes/` + `templates/` | `~/.local/share/lince/lince-lab/` |
| Claude skill | `~/.claude/skills/lince-lab/` |
| Default config (only if absent) | `~/.config/lince-lab/config.toml` |
| Broker runtime socket | `~/.agent-sandbox/lince-lab.sock` |

`update.sh` re-copies everything **except** your config; `uninstall.sh` removes
the CLI, the share dir, and the skill (leaving your config in place).

If `~/.local/bin` is not on your `PATH`, the installer warns (it does not fail)
and tells you the line to add to your shell profile.

## The CLI — five command groups

`lince-lab` is a single argparse CLI with **two-level grouped help**: the
top-level `--help` lists the groups, and `lince-lab <group> --help` drills into a
group's verbs.

| Group | Purpose | Verbs |
|---|---|---|
| `vm` | Manage disposable lab VMs | `up`, `down`, `status`, `list`, `exec`, `copy`, `snapshot {create,apply,delete,list}`, `rm` |
| `run` | Run a recipe end-to-end (the everyday entry point) | `validate`, `recipe`, `presets` |
| `find` | Autonomous regression hunting | `bisect` |
| `watch` | Observe a VM's terminal | `grab`, `keys`, `wait` |
| `lab` | Broker & setup plumbing | `broker {start,stop,status}`, `doctor`, `version` |

Every verb is a thin call to the host-side broker over the unix socket; the CLI
exits with the **guest / recipe exit code** verbatim (`vm exec`, `run recipe`,
`find bisect`), which is what makes bisect and CI-style oracle chaining work.

## Quick start

```bash
# 1. Start the broker (host process; uses Lima, or a no-VM fake when testing).
lince-lab lab broker start &

# 2. Check it is reachable and prerequisites are present.
lince-lab lab doctor

# 3. Validate then run a shipped recipe end-to-end.
lince-lab run validate ~/.local/share/lince/lince-lab/recipes/generic-npm.toml
lince-lab run recipe   ~/.local/share/lince/lince-lab/recipes/generic-npm.toml

# 4. Drive a disposable VM by hand.
lince-lab vm up lince-lab-demo
lince-lab vm exec lince-lab-demo -- sh -c 'echo hello'   # exits with the guest code
lince-lab vm snapshot create lince-lab-demo clean
lince-lab vm rm lince-lab-demo

# 5. Hunt a regression: the recipe is the verdict oracle.
lince-lab find bisect ~/.local/share/lince/lince-lab/recipes/lince-wizard.toml \
    --good v1.0 --bad HEAD --repo-dir /path/to/repo --out bisect.json
```

## Presets

`lince-lab run presets` lists three named presets that tune only resource /
network / lifecycle knobs. Security invariants (no host mounts, no credential
injection, name-prefixing) are **non-overridable policy**, never preset config.

| Preset | Use it for |
|---|---|
| **`quick`** | Smoke-testing a single command or recipe. 1 CPU / 1 GiB / 10 GiB, network denied, VM auto-deleted, no base snapshot retained. "Does this even run?" |
| **`bisect`** | The autonomous regression loop. 2 CPU / 2 GiB, base snapshot **retained** for fast per-candidate reset, network denied, longer per-step timeout. Pair with `find bisect`. |
| **`networked`** | Recipes that legitimately must fetch (npm / pip). 2 CPU / 2 GiB, networking allowed but **only** the recipe's explicit `allow_hosts` / `allow_ports`; everything else stays denied, no host credentials. |

## macOS backend (Tart) — experimental

On Apple Silicon, lince-lab can boot a clean disposable **macOS** guest to
exercise the Seatbelt sandbox path (Epic #268). It is selected with
`LINCE_LAB_MACOS=1` when starting the broker and drives
[Tart](https://tart.run) over Virtualization.framework.

Requirements:

- Apple Silicon Mac (`uname -m` = `arm64`).
- `tart`: `brew install cirruslabs/cli/tart`.
  - Homebrew 6+ may refuse the tap with a *tap-trust* error; run
    `brew trust cirruslabs/cli` (or, one-shot,
    `HOMEBREW_NO_REQUIRE_TAP_TRUST=1 brew install cirruslabs/cli/tart`).
- A base image: `tart pull ghcr.io/cirruslabs/macos-sequoia-base:latest`.

Run a guest:

```bash
LINCE_LAB_MACOS=1 lince-lab lab broker start &
lince-lab vm up lince-lab-demo --image macos-sequoia
lince-lab vm exec lince-lab-demo -- sw_vers
lince-lab vm rm lince-lab-demo -f
```

Reset uses APFS copy-on-write `tart clone` of a stopped golden guest (vz has no
snapshots). The macOS/arm64 `ht` capture binary installs to
`~/.local/share/lince/lince-lab/bin/ht-darwin`.

## Documentation

- Design & decisions: [`docs/design/lince-lab-design.md`](../docs/design/lince-lab-design.md)
- User docs (recipes, presets, capture, bisect): [`docs/documentation/lince-lab/`](../docs/documentation/lince-lab/)
