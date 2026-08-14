#!/usr/bin/env bash
# event-map-coverage.sh — Verify agents-defaults.toml event_map invariants.
#
# Rules enforced (LINCE-118 / LINCE-122):
#   1. Every [agents.<name>] with `has_native_hooks = true` MUST have an
#      [agents.<name>.event_map] section (otherwise raw native events would
#      always fall back to Unknown).
#   2. Every value inside any event_map MUST be one of the 5 canonical
#      lowercase strings: unknown | running | input | permission | stopped.
#   3. The hook script the agent depends on must exist on disk. Mapping:
#        claude*    -> hooks/claude-status-hook.sh
#        codex*     -> hooks/codex-status-hook.sh
#        opencode*  -> hooks/opencode-status-hook.js
#        pi*        -> hooks/pi/lince-pi-hook.ts
#
# Exit code:
#   0 — no violations
#   1 — at least one violation

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
TOML="${DASHBOARD_DIR}/agents-defaults.toml"
HOOKS_DIR="${DASHBOARD_DIR}/hooks"

if [ ! -f "$TOML" ]; then
    echo "FAIL: agents-defaults.toml not found at $TOML"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "FAIL: python3 required"
    exit 1
fi

python3 - "$TOML" "$HOOKS_DIR" <<'PY'
import os
import re
import sys

toml_path, hooks_dir = sys.argv[1], sys.argv[2]

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        print("FAIL: tomllib/tomli required (Python 3.11+ or install tomli)")
        sys.exit(1)

with open(toml_path, "rb") as f:
    data = tomllib.load(f)

agents = data.get("agents") or {}
canonical = {"unknown", "running", "input", "permission", "stopped"}

# Map agent name prefix → hook script that must exist.
def hook_for(name: str) -> str | None:
    # Strip -unsandboxed suffix for matching.
    base = re.sub(r"-unsandboxed$", "", name)
    if base.startswith("claude"):
        return "claude-status-hook.sh"
    if base.startswith("codex"):
        return "codex-status-hook.sh"
    if base.startswith("bob"):
        return "bob-status-hook.sh"
    if base.startswith("opencode"):
        return "opencode-status-hook.js"
    if base.startswith("pi"):
        return "pi/lince-pi-hook.ts"
    # gemini, bash, zsh, fish: has_native_hooks=false, no hook expected.
    return None

violations: list[str] = []
checked_agents = 0
checked_mappings = 0

for name, cfg in sorted(agents.items()):
    if not isinstance(cfg, dict):
        continue
    has_hooks = bool(cfg.get("has_native_hooks", False))
    event_map = cfg.get("event_map") or {}

    if has_hooks:
        checked_agents += 1
        if not event_map:
            violations.append(
                f"[agents.{name}] has_native_hooks=true but no event_map section"
            )
        # Validate hook script existence.
        expected = hook_for(name)
        if expected is not None:
            path = os.path.join(hooks_dir, expected)
            if not os.path.exists(path):
                violations.append(
                    f"[agents.{name}] expected hook script missing: {path}"
                )
    else:
        # Agents without native hooks may still have an event_map (unusual but
        # not forbidden). Just validate any values found.
        pass

    for key, value in event_map.items():
        checked_mappings += 1
        if not isinstance(value, str):
            violations.append(
                f"[agents.{name}.event_map] {key!r} -> {value!r}: not a string"
            )
            continue
        if value not in canonical:
            violations.append(
                f"[agents.{name}.event_map] {key!r} -> {value!r}: "
                f"not one of {sorted(canonical)}"
            )

# Report
print(f"Scanned {len(agents)} agent entries "
      f"({checked_agents} with has_native_hooks=true), "
      f"{checked_mappings} event_map values.")

if violations:
    print()
    print(f"{len(violations)} violation(s):")
    for v in violations:
        print(f"  - {v}")
    sys.exit(1)
else:
    print("All event_map entries are canonical and every has_native_hooks agent "
          "has a hook script + event_map.")
    sys.exit(0)
PY
