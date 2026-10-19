#!/usr/bin/env bash
# Real namespace gate: run from the source tree; only disposable paths are used.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX="$HERE/../agent-sandbox"
WORK="$(mktemp -d /tmp/lince-mask-test.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

for tool in unshare mount bwrap python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "FAIL: missing required test dependency: $tool" >&2
        exit 1
    fi
done

# Probe capability before treating any subsequent launch failure as a test failure.
if unshare -Urmpf -- mount -t tmpfs tmpfs "$WORK" 2>"$WORK/probe-error"; then
    :
else
    probe_status=$?
    probe_error="$(<"$WORK/probe-error")"
    detail="${probe_error,,}"
    first_line="${detail%%$'\n'*}"
    # unshare exits 1 for a denied user namespace; mount exits 32 when the
    # namespace lacks CAP_SYS_ADMIN. Other failures are broken gates, not SKIPs.
    if [[ "$probe_status" -eq 1 && "$first_line" == unshare:* &&
          ( "$first_line" == *"operation not permitted"* || "$first_line" == *"permission denied"* ||
            "$first_line" == *"eperm"* ) ]] ||
       [[ "$probe_status" -eq 32 && "$first_line" == mount:* &&
          ( "$first_line" == *"operation not permitted"* || "$first_line" == *"permission denied"* ||
            "$first_line" == *"eperm"* ) ]]; then
        echo "SKIP: private user/mount namespace capability denied (exit $probe_status): $probe_error"
        exit 0
    fi
    echo "FAIL: private user/mount namespace probe failed (exit $probe_status): $probe_error" >&2
    exit 1
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
    local point="$1" probe="$2" landlock="$3" command="${4:-python3}" auto_path="${5:-false}"
    printf '[sandbox]\nbackend = "agent-sandbox"\nauto_expose_path = %s\npersist_toolchains = false\nmask_mount_points = %s\n[security]\nlandlock = %s\nblock_git_push = false\n[agents.mask-probe]\ncommand = "%s"\ndefault_args = ["%s"]\n' \
        "$auto_path" "$point" "$landlock" "$command" "$probe" > "$HOME/.agent-sandbox/config.toml"
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

# An executable from masked HOME outside the project must be refused before
# the probe executes. Exercise both direct entry points, not just argv tests.
PROJECT="$FIXTURE/plain/project"
mkdir -p "$HOME/.local/bin"
HIDDEN_AGENT="$HOME/.local/bin/my-agent"
printf '#!/bin/sh\nprintf ran > "%s"\n' "$PROJECT/hidden-agent-ran" > "$HIDDEN_AGENT"
chmod +x "$HIDDEN_AGENT"
for spelling in absolute path; do
    if [[ "$spelling" == absolute ]]; then
        write_config "[\"$HOME\"]" "$PROJECT/mount_mask_probe.py" false "$HIDDEN_AGENT"
    else
        write_config "[\"$HOME\"]" "$PROJECT/mount_mask_probe.py" false my-agent true
    fi
    for command in run learn; do
        rm -f "$PROJECT/hidden-agent-ran"
        if [[ "$command" == run ]]; then
            if ( cd "$HOME" && PATH="$HOME/.local/bin:$PATH" python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe ) \
                >"$WORK/hidden-$spelling-run.log" 2>&1; then
                echo "FAIL: run launched masked executable" >&2; exit 1
            fi
        else
            if ( cd "$PROJECT" && PATH="$HOME/.local/bin:$PATH" python3 "$SANDBOX" learn --agent mask-probe --duration 5 ) \
                >"$WORK/hidden-$spelling-learn.log" 2>&1; then
                echo "FAIL: learn launched masked executable" >&2; exit 1
            fi
        fi
        test ! -e "$PROJECT/hidden-agent-ran"
        if ! grep -q 'Error: .*my-agent.*mask_mount_points hides a required executable' \
            "$WORK/hidden-$spelling-$command.log"; then
            echo "FAIL: $command did not explicitly refuse masked executable" >&2; exit 1
        fi
        echo "PASS: $command refuses masked HOME executable ($spelling) before agent exec"
    done
done

# The same legacy global config is encountered at the invocation/learn root
# when launching from HOME; it must not be mistaken for a local override.
POINT="$FIXTURE/plain"
write_config "[\"$POINT\"]" "$PROJECT/mount_mask_probe.py" false
( cd "$HOME" && python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe ) >"$WORK/home-run.log" 2>&1
test "$(<"$PROJECT/persisted")" = yes
echo "PASS: run from HOME with -p loads the global legacy mask"
printf 'from pathlib import Path\n(Path.home() / "learn-home-ran").write_text("yes")\n' > "$HOME/home_probe.py"
write_config "[\"$POINT\"]" "$HOME/home_probe.py" false
( cd "$HOME" && python3 "$SANDBOX" learn --agent mask-probe --duration 5 ) >"$WORK/home-learn.log" 2>&1
test "$(<"$HOME/learn-home-ran")" = yes
echo "PASS: learn from HOME loads the global legacy mask"

# A generated Claude bind can contain a directory symlink. The link is
# followed in the *sandbox* namespace, where .local is masked, even though
# the host can resolve the executable in that directory.
SAFE="$FIXTURE/safe"
mkdir -p "$SAFE" "$HOME/.local/bin"
printf '#!/bin/sh\nprintf ran > "%s"\n' "$PROJECT/alias-agent-ran" > "$HOME/.local/bin/my-agent"
chmod +x "$HOME/.local/bin/my-agent"
ln -s "$HOME/.local/bin" "$SAFE/linkdir"
write_config "[\"$HOME/.local\"]" "$PROJECT/mount_mask_probe.py" false "$HOME/.claude/linkdir/my-agent"
printf '\n[claude]\nconfig_dir = "%s"\n' "$SAFE" >> "$HOME/.agent-sandbox/config.toml"
rm -f "$PROJECT/alias-agent-ran"
if ( cd "$WORK" && python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe ) \
    >"$WORK/hidden-bound-alias.log" 2>&1; then
    echo "FAIL: bound parent symlink launched masked executable" >&2; exit 1
fi
test ! -e "$PROJECT/alias-agent-ran"
if ! grep -q 'Error: .*my-agent.*mask_mount_points hides a required executable' \
    "$WORK/hidden-bound-alias.log"; then
    echo "FAIL: bound parent symlink was not refused before agent exec" >&2; exit 1
fi
echo "PASS: bound parent symlink into masked HOME refused before agent exec"

# The same bound symlink is valid when it points to the project bind.
printf '#!/bin/sh\nprintf ran > "%s"\n' "$PROJECT/alias-agent-ran" > "$PROJECT/my-agent"
chmod +x "$PROJECT/my-agent"
rm "$SAFE/linkdir"
ln -s "$PROJECT" "$SAFE/linkdir"
( cd "$WORK" && python3 "$SANDBOX" run -p "$PROJECT" --agent mask-probe ) \
    >"$WORK/visible-bound-alias.log" 2>&1
test "$(<"$PROJECT/alias-agent-ran")" = ran
echo "PASS: bound parent symlink to remounted project executes"
NAMESPACE
