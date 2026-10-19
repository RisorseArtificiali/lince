#!/usr/bin/env bash
# Real namespace gate: run from the source tree; only disposable paths are used.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX="$HERE/../agent-sandbox"
WORK="$(mktemp -d /tmp/lince-mask-test.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

for tool in unshare mount bwrap python3 strace; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "SKIP: missing namespace/mount test dependency: $tool"
        exit 0
    fi
done

# Probe capability before treating any subsequent launch failure as a test failure.
if ! unshare -Urmpf -- mount -t tmpfs tmpfs "$WORK" 2>"$WORK/probe-error"; then
    echo "SKIP: private user/mount namespace cannot mount tmpfs: $(<"$WORK/probe-error")"
    exit 0
fi

unshare -Urmpf --mount-proc -- bash -euo pipefail -s -- "$WORK" "$HERE" "$SANDBOX" <<'NAMESPACE'
WORK="$1"; HERE="$2"; SANDBOX="$3"
mount --make-rprivate /
mount -t tmpfs tmpfs /run/user
mkdir -p /run/user/0
mount -t tmpfs tmpfs /mnt
FIXTURE="/mnt/lince-mask-test.$$"
mkdir -p "$FIXTURE/point" "$FIXTURE/plain" "$WORK/home/.agent-sandbox/claude-config"
mount -t tmpfs tmpfs "$FIXTURE/point"
export HOME="$WORK/home"
export XDG_CONFIG_HOME="$HOME/.config"
export LINCE_STATUS_DIR="$WORK/status"
mkdir -p "$LINCE_STATUS_DIR"
mkdir -p "$HOME/.agent-sandbox/profiles"
cp "$HERE/../profiles/claude-permissive.toml" "$HOME/.agent-sandbox/profiles/mask-probe-permissive.toml"
cp "$HERE/../profiles/claude-paranoid.toml" "$HOME/.agent-sandbox/profiles/mask-probe-paranoid.toml"

write_config() {
    local point="$1" probe="$2" landlock="$3"
    printf '[sandbox]\nbackend = "agent-sandbox"\nauto_expose_path = false\npersist_toolchains = false\nmask_mount_points = %s\n[security]\nlandlock = %s\nblock_git_push = false\n[agents.mask-probe]\ncommand = "python3"\ndefault_args = ["%s"]\n' \
        "$point" "$landlock" "$probe" > "$HOME/.agent-sandbox/config.toml"
}

for kind in point plain; do
    POINT="$FIXTURE/$kind"
    ln -sfn "$POINT" "$FIXTURE/alias"
    PROJECT="$POINT/project"
    mkdir -p "$PROJECT" "$POINT/sibling" "$POINT/outside"
    printf 'project' > "$PROJECT/inside"
    printf 'secret' > "$POINT/sibling/secret"
    cp "$HERE/mount_mask_probe.py" "$PROJECT/mount_mask_probe.py"
    cat > "$PROJECT/visible_probe.py" <<'VISIBLE'
from pathlib import Path
project = Path(__file__).resolve().parent
assert (project.parent / 'sibling/secret').read_text() == 'secret'
assert (project / 'inside').read_text() == 'project'
(project / 'baseline-ran').write_text('yes')
VISIBLE

    # No policy: sibling is still visible. Verify agent exec, not just bwrap startup.
    write_config '[]' "$PROJECT/visible_probe.py" false
    ( cd "$WORK" && python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe )
    test "$(<"$PROJECT/baseline-ran")" = yes
    echo "PASS: $kind no-list baseline sees sibling"

    for landlock in true false; do
        write_config "[\"$POINT\"]" "$PROJECT/mount_mask_probe.py" "$landlock"
        for level in normal permissive paranoid; do
            rm -f "$PROJECT/persisted" "$POINT/ephemeral"
            if [[ "$level" == paranoid ]]; then
                ( cd "$WORK" && env -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN \
                    ANTHROPIC_API_KEY=mask-probe-nonfunctional-test-only \
                    python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe --sandbox-level "$level" )
            else
                ( cd "$WORK" && python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe --sandbox-level "$level" )
            fi
            test "$(<"$PROJECT/persisted")" = yes
            test ! -e "$POINT/ephemeral"
            echo "PASS: $kind $level landlock=$landlock hides siblings, persists project, isolates write"
        done
    done

    # learn uses cwd as project. Exit status alone is insufficient: check the
    # marker, or confirm that a refusal happened before the probe could exec.
    write_config "[\"$POINT\"]" "$PROJECT/mount_mask_probe.py" true
    rm -f "$PROJECT/persisted" "$POINT/ephemeral"
    if ( cd "$PROJECT" && python3 "$SANDBOX" learn --agent mask-probe --duration 5 ) >"$WORK/learn.log" 2>&1; then
        test "$(<"$PROJECT/persisted")" = yes
        test ! -e "$POINT/ephemeral"
        echo "PASS: $kind learn hides siblings and persists project"
    else
        test ! -e "$PROJECT/persisted"
        if ! grep -q 'Error: .*mask_mount_points\|Error: .*masked' "$WORK/learn.log"; then
            echo "FAIL: learn did not exec and did not explicitly refuse overlap" >&2
            exit 1
        fi
        echo "PASS: $kind learn refused before agent exec"
    fi

    if [[ "$kind" == point ]]; then
        # Learn normally binds HOME rw. Exercise the dangerous overlap with a
        # disposable HOME equal to the masked point, without touching real HOME.
        mkdir -p "$POINT/.agent-sandbox"
        cp "$HOME/.agent-sandbox/config.toml" "$POINT/.agent-sandbox/config.toml"
        rm -f "$PROJECT/persisted" "$POINT/ephemeral"
        if ( cd "$PROJECT" && HOME="$POINT" XDG_CONFIG_HOME="$POINT/.config" \
            python3 "$SANDBOX" learn --agent mask-probe --duration 5 ) >"$WORK/learn-home.log" 2>&1; then
            test "$(<"$PROJECT/persisted")" = yes
            test ! -e "$POINT/ephemeral"
            test "$(<"$POINT/sibling/secret")" = secret
            echo "PASS: learn HOME overlap hides sibling, persists project, isolates write"
        else
            test ! -e "$PROJECT/persisted"
            test ! -e "$POINT/ephemeral"
            if ! grep -Eq 'Error: .*would (re-expose a masked path|expose masked)' \
                "$WORK/learn-home.log"; then
                echo "FAIL: learn HOME overlap did not exec and did not explicitly refuse masked overlap" >&2
                exit 1
            fi
            echo "PASS: learn HOME overlap refused before agent exec"
        fi
    fi
done
NAMESPACE
