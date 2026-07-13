#!/usr/bin/env bash
#
# LINCE Quickstart Installer
#
# Interactive TUI installer for LINCE — sandbox + dashboard for AI coding agents.
#
# Usage:
#   ./quickstart.sh              # Interactive TUI
#   ./quickstart.sh --defaults   # Install with defaults (all agents, bwrap, sandbox)
#   ./quickstart.sh --help       # Show help
#
# Exit codes:
#   0 - Success
#   1 - Error
#   2 - Cancelled by user
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors & formatting ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── State ────────────────────────────────────────────────────────────
SELECTED_BACKENDS=()       # populated by select_backends(): "bwrap", "seatbelt", "nono", "unsandboxed"
SELECTED_AGENTS=()
INSTALL_VOXCODE=false
INSTALL_LINCE_LAB=false
USE_DEFAULTS=false

# Available agents: key|display_name|description
AGENTS=(
    "claude|Claude Code|Anthropic's AI coding agent"
    "codex|OpenAI Codex|OpenAI's coding agent (CLI)"
    "bob|Bob|IBM's AI coding agent (CLI)"
    "gemini|Google Gemini CLI|Google's AI coding agent"
    "opencode|OpenCode|Open-source coding agent"
    "pi|Pi|Minimal coding agent (https://pi.dev)"
    "goose|Goose|Open-source AI agent by AAIF"
)
# Track selection state (1=selected, 0=not)
AGENT_SELECTED=(1 1 0 0 0 0)  # claude and codex on by default

# Available backends: key|display_name|description|installed
BACKENDS=(
    "bwrap|bubblewrap (bwrap)|Built-in sandbox. Same technology as Flatpak. Minimal, zero dependencies."
    "seatbelt|Seatbelt (sandbox-exec)|macOS native sandbox, built into the OS. Zero dependencies. Replaces nono on macOS."
    "nono|nono (nono.sh) — deprecated|Legacy external sandbox. Superseded by Seatbelt on macOS. Kept for compatibility."
    "unsandboxed|Unsandboxed|No isolation — agent runs with full host access."
)
# Track backend selection state (1=selected, 0=not)
BACKEND_SELECTED=(1 0 0 0)  # bwrap on by default

# Shell agents (gh#91): key|display|description. Pre-selection is computed
# at runtime from $SHELL by select_shells() so it tracks the host's actual
# default shell instead of hard-coding bash.
SHELLS=(
    "bash|Bash|GNU bash — Linux default shell"
    "zsh|Zsh|Z shell — macOS default shell"
    "fish|Fish|Friendly interactive shell — auto-suggestions, syntax highlighting"
)
SHELL_SELECTED=(0 0 0)
SELECTED_SHELLS=()         # ordered subset of {bash,zsh,fish}
DEFAULT_SHELL=""           # one of SELECTED_SHELLS, used by the tiled placeholder
DEFAULT_SHELL_BIN=""       # absolute path resolved via `command -v`

# ── Helpers ──────────────────────────────────────────────────────────
confirm() {
    local prompt="$1"
    read -p "$prompt (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ╦  ╦╔╗╔╔═╗╔═╗"
    echo "  ║  ║║║║║  ║╣ "
    echo "  ╩═╝╩╝╚╝╚═╝╚═╝"
    echo -e "${NC}"
    echo -e "  ${BOLD}Secure Multi-Agent Coding Workstation${NC}"
    echo -e "  ${DIM}https://lince.sh${NC}"
    echo ""
}

print_separator() {
    echo -e "${DIM}────────────────────────────────────────────────────${NC}"
}

# Move cursor up N lines and clear to end of screen — used by the
# multi-select TUIs to redraw their menu in place.
redraw_up() {
    echo -en "\033[$1A\033[J"
}

# ── TUI: Backend selection (multi-select) ───────────────────────────
select_backends() {
    local OS_NAME
    OS_NAME="$(uname -s)"

    echo ""
    echo -e "${BOLD}Step 1: Sandbox backends${NC}"
    echo ""
    echo -e "  LINCE can wrap each AI agent in a sandbox so it can code"
    echo -e "  freely without reaching your SSH keys, credentials, or"
    echo -e "  pushing to production."
    echo ""
    echo -e "  ${DIM}These are NOT mutually exclusive — select all the backends${NC}"
    echo -e "  ${DIM}you want available. When you spawn an agent, you pick one${NC}"
    echo -e "  ${DIM}backend for that agent. Different agents can use different backends.${NC}"
    echo ""

    # On macOS, bwrap is not available — pre-select seatbelt instead
    if [ "$OS_NAME" = "Darwin" ]; then
        BACKEND_SELECTED=(0 1 0 0)  # seatbelt only
        echo -e "  ${DIM}macOS detected — bubblewrap is Linux-only, Seatbelt (sandbox-exec) pre-selected.${NC}"
        echo ""
    fi

    # Detect installed backends
    local has_bwrap=false has_seatbelt=false has_nono=false
    command -v bwrap >/dev/null 2>&1 && has_bwrap=true
    # Seatbelt is sandbox-exec, built into macOS
    [ -x /usr/bin/sandbox-exec ] && has_seatbelt=true
    command -v nono >/dev/null 2>&1 && has_nono=true

    echo -e "  ${DIM}Toggle with number keys, press Enter when done:${NC}"
    echo ""

    while true; do
        for i in "${!BACKENDS[@]}"; do
            IFS='|' read -r key name desc <<< "${BACKENDS[$i]}"
            # Color: unsandboxed in red, sandboxed in green
            local color="$GREEN"
            local tag="✓"
            if [ "$key" = "unsandboxed" ]; then
                color="$RED"
                tag="!"
            fi
            # Installed status
            local status=""
            case "$key" in
                bwrap)
                    if [ "$has_bwrap" = true ]; then status=" ${GREEN}(installed)${NC}"
                    else status=" ${YELLOW}(not installed)${NC}"; fi
                    # Hide on macOS
                    if [ "$OS_NAME" = "Darwin" ]; then
                        echo -e "  ${DIM}[ ] $((i+1))) $name — Linux only${NC}"
                        continue
                    fi
                    ;;
                seatbelt)
                    if [ "$has_seatbelt" = true ]; then status=" ${GREEN}(built-in)${NC}"
                    else status=" ${YELLOW}(requires macOS 10.5+)${NC}"; fi
                    # Hide on Linux
                    if [ "$OS_NAME" != "Darwin" ]; then
                        echo -e "  ${DIM}[ ] $((i+1))) $name — macOS only${NC}"
                        continue
                    fi
                    ;;
                nono)
                    if [ "$has_nono" = true ]; then status=" ${RED}(deprecated)${NC}"
                    else status=" ${YELLOW}(not installed — deprecated, consider Seatbelt on macOS)${NC}"; fi
                    ;;
            esac

            if [ "${BACKEND_SELECTED[$i]}" = "1" ]; then
                echo -e "  ${color}[${tag}]${NC} ${BOLD}$((i+1))) $name${NC} ${DIM}— $desc${NC}${status}"
            else
                echo -e "  ${DIM}[ ] $((i+1))) $name — $desc${NC}${status}"
            fi
        done
        echo ""
        echo -e "  ${DIM}Press 1-${#BACKENDS[@]} to toggle, Enter to confirm${NC}"
        read -p "  > " -n 1 -r
        echo ""

        case "$REPLY" in
            [1-9])
                local idx=$((REPLY - 1))
                if [ $idx -lt ${#BACKENDS[@]} ]; then
                    # On macOS, don't allow selecting bwrap; on Linux, don't allow seatbelt
                    IFS='|' read -r key _ _ <<< "${BACKENDS[$idx]}"
                    if [ "$key" = "bwrap" ] && [ "$OS_NAME" = "Darwin" ]; then
                        echo -e "  ${YELLOW}bubblewrap is not available on macOS${NC}"
                    elif [ "$key" = "seatbelt" ] && [ "$OS_NAME" != "Darwin" ]; then
                        echo -e "  ${YELLOW}Seatbelt (sandbox-exec) is only available on macOS${NC}"
                    else
                        if [ "${BACKEND_SELECTED[$idx]}" = "1" ]; then
                            BACKEND_SELECTED[$idx]=0
                        else
                            BACKEND_SELECTED[$idx]=1
                        fi
                    fi
                fi
                ;;
            "")
                # Enter pressed — validate and confirm
                local count=0
                for sel in "${BACKEND_SELECTED[@]}"; do
                    [ "$sel" = "1" ] && count=$((count + 1))
                done
                if [ $count -eq 0 ]; then
                    echo -e "  ${RED}At least one backend must be selected.${NC}"
                    echo ""
                    continue
                fi
                break
                ;;
        esac

        redraw_up $(( ${#BACKENDS[@]} + 3 ))
    done

    # Build selected backends list
    SELECTED_BACKENDS=()
    for i in "${!BACKENDS[@]}"; do
        if [ "${BACKEND_SELECTED[$i]}" = "1" ]; then
            IFS='|' read -r key _ _ <<< "${BACKENDS[$i]}"
            SELECTED_BACKENDS+=("$key")
        fi
    done

    # If ONLY unsandboxed selected, show big warning
    if [ ${#SELECTED_BACKENDS[@]} -eq 1 ] && [ "${SELECTED_BACKENDS[0]}" = "unsandboxed" ]; then
        echo ""
        echo -e "${RED}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}${BOLD}║                    ⚠  WARNING  ⚠                    ║${NC}"
        echo -e "${RED}${BOLD}╠══════════════════════════════════════════════════════╣${NC}"
        echo -e "${RED}${BOLD}║                                                      ║${NC}"
        echo -e "${RED}${BOLD}║  Without sandboxing, AI agents have FULL ACCESS to:   ║${NC}"
        echo -e "${RED}${BOLD}║                                                      ║${NC}"
        echo -e "${RED}${BOLD}║    • Your SSH keys and GPG keys                      ║${NC}"
        echo -e "${RED}${BOLD}║    • Cloud credentials (AWS, GCP, Azure)              ║${NC}"
        echo -e "${RED}${BOLD}║    • Git push to any remote                          ║${NC}"
        echo -e "${RED}${BOLD}║    • All files on your system                        ║${NC}"
        echo -e "${RED}${BOLD}║    • Running processes and network                   ║${NC}"
        echo -e "${RED}${BOLD}║                                                      ║${NC}"
        echo -e "${RED}${BOLD}║  A single hallucinated command could:                ║${NC}"
        echo -e "${RED}${BOLD}║    • Push untested code to production                ║${NC}"
        echo -e "${RED}${BOLD}║    • Delete or modify critical files                 ║${NC}"
        echo -e "${RED}${BOLD}║    • Leak credentials to third parties               ║${NC}"
        echo -e "${RED}${BOLD}║                                                      ║${NC}"
        echo -e "${RED}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${RED}${BOLD}  Are you sure you want to proceed with ONLY unsandboxed?${NC}"
        read -p "  Type 'yes' to confirm (anything else cancels): " -r
        if [ "$REPLY" != "yes" ]; then
            echo ""
            echo -e "  ${GREEN}Good choice. Please re-select backends.${NC}"
            # Reset to bwrap default and re-run
            BACKEND_SELECTED=(1 0 0 0)
            select_backends
            return
        fi
    fi

    echo -e "  ${GREEN}✓${NC} Backends: ${BOLD}${SELECTED_BACKENDS[*]}${NC}"
}

# Helper: check if a backend is selected
has_backend() {
    local target="$1"
    for b in "${SELECTED_BACKENDS[@]}"; do
        [ "$b" = "$target" ] && return 0
    done
    return 1
}

# ── TUI: Agent selection ─────────────────────────────────────────────
select_agents() {
    echo ""
    print_separator
    echo -e "${BOLD}Step 2: Select agents to configure${NC}"
    echo ""
    echo -e "  ${DIM}These are sandboxing wrappers and dashboard entries for each agent.${NC}"
    echo -e "  ${DIM}The agents themselves (claude, codex, gemini, etc.) must be${NC}"
    echo -e "  ${DIM}installed separately — that is outside the scope of this installer.${NC}"
    echo ""
    echo -e "  ${DIM}Toggle with number keys, press Enter when done:${NC}"
    echo ""

    while true; do
        for i in "${!AGENTS[@]}"; do
            IFS='|' read -r key name desc <<< "${AGENTS[$i]}"
            if [ "${AGENT_SELECTED[$i]}" = "1" ]; then
                echo -e "  ${GREEN}[x]${NC} ${BOLD}$((i+1))) $name${NC} ${DIM}— $desc${NC}"
            else
                echo -e "  ${DIM}[ ] $((i+1))) $name — $desc${NC}"
            fi
        done
        echo ""
        echo -e "  ${DIM}Press 1-${#AGENTS[@]} to toggle, Enter to confirm, 'a' for all, 'n' for none${NC}"
        read -p "  > " -n 1 -r
        echo ""

        case "$REPLY" in
            [1-9])
                local idx=$((REPLY - 1))
                if [ $idx -lt ${#AGENTS[@]} ]; then
                    if [ "${AGENT_SELECTED[$idx]}" = "1" ]; then
                        AGENT_SELECTED[$idx]=0
                    else
                        AGENT_SELECTED[$idx]=1
                    fi
                fi
                ;;
            a|A)
                for i in "${!AGENTS[@]}"; do AGENT_SELECTED[$i]=1; done
                ;;
            n|N)
                for i in "${!AGENTS[@]}"; do AGENT_SELECTED[$i]=0; done
                ;;
            "")
                # Enter pressed — confirm selection
                break
                ;;
        esac

        redraw_up $(( ${#AGENTS[@]} + 3 ))
    done

    # Build selected agents list
    SELECTED_AGENTS=()
    for i in "${!AGENTS[@]}"; do
        if [ "${AGENT_SELECTED[$i]}" = "1" ]; then
            IFS='|' read -r key _ _ <<< "${AGENTS[$i]}"
            SELECTED_AGENTS+=("$key")
        fi
    done

    if [ ${#SELECTED_AGENTS[@]} -eq 0 ]; then
        echo -e "  ${YELLOW}No agents selected. The dashboard will be installed${NC}"
        echo -e "  ${YELLOW}but no agent types will be pre-configured.${NC}"
        echo -e "  ${DIM}You can add agents later via /lince-add-supported-agent or config.toml.${NC}"
    else
        echo -e "  ${GREEN}✓${NC} Selected: ${BOLD}${SELECTED_AGENTS[*]}${NC}"
    fi
}

# ── TUI: Shell selection (multi-select) + default shell ─────────────
#
# Configures the gh#91 shell agents. Picks (a) which shells become dashboard
# agents and (b) which one runs in the tiled layout's right-hand placeholder
# pane (the ASCII-art viewport B). Pre-selection follows `$SHELL`: a user
# whose login shell is zsh sees zsh pre-checked, etc.
select_shells() {
    echo ""
    print_separator
    echo -e "${BOLD}Step 3: Select shell agents${NC}"
    echo ""
    echo -e "  ${DIM}Shell agents open a raw shell pane in the project dir —${NC}"
    echo -e "  ${DIM}useful for quick command execution alongside coding agents.${NC}"
    echo -e "  ${DIM}Skip this step (Enter with nothing selected) if you don't want any.${NC}"
    echo ""

    # Auto-detect host shell and pre-check the matching entry. basename($SHELL)
    # so "/usr/bin/zsh" → "zsh". Falls back to bash if $SHELL is unset/unknown.
    local host_shell
    host_shell=$(basename "${SHELL:-/bin/bash}" 2>/dev/null)
    for i in "${!SHELLS[@]}"; do
        IFS='|' read -r key _ _ <<< "${SHELLS[$i]}"
        if [ "$key" = "$host_shell" ]; then
            SHELL_SELECTED[$i]=1
        fi
    done
    # If $SHELL didn't match any of our entries (e.g. dash, ksh), fall back
    # to bash — universally available, safe default.
    local any_preselected=0
    for v in "${SHELL_SELECTED[@]}"; do
        [ "$v" = "1" ] && any_preselected=1
    done
    if [ "$any_preselected" = "0" ]; then
        SHELL_SELECTED[0]=1   # bash
    fi

    echo -e "  ${DIM}Toggle with number keys, press Enter when done:${NC}"
    echo ""

    while true; do
        for i in "${!SHELLS[@]}"; do
            IFS='|' read -r key name desc <<< "${SHELLS[$i]}"
            local marker=""
            if command -v "$key" >/dev/null 2>&1; then
                marker="${GREEN}(installed)${NC}"
            else
                marker="${YELLOW}(not in PATH)${NC}"
            fi
            if [ "${SHELL_SELECTED[$i]}" = "1" ]; then
                echo -e "  ${GREEN}[x]${NC} ${BOLD}$((i+1))) $name${NC} ${DIM}— $desc${NC} $marker"
            else
                echo -e "  ${DIM}[ ] $((i+1))) $name — $desc${NC} $marker"
            fi
        done
        echo ""
        echo -e "  ${DIM}Press 1-${#SHELLS[@]} to toggle, Enter to confirm, 'a' for all, 'n' for none${NC}"
        read -p "  > " -n 1 -r
        echo ""

        case "$REPLY" in
            [1-9])
                local idx=$((REPLY - 1))
                if [ $idx -lt ${#SHELLS[@]} ]; then
                    if [ "${SHELL_SELECTED[$idx]}" = "1" ]; then
                        SHELL_SELECTED[$idx]=0
                    else
                        SHELL_SELECTED[$idx]=1
                    fi
                fi
                ;;
            a|A)
                for i in "${!SHELLS[@]}"; do SHELL_SELECTED[$i]=1; done
                ;;
            n|N)
                for i in "${!SHELLS[@]}"; do SHELL_SELECTED[$i]=0; done
                ;;
            "")
                break
                ;;
        esac

        redraw_up $(( ${#SHELLS[@]} + 3 ))
    done

    SELECTED_SHELLS=()
    for i in "${!SHELLS[@]}"; do
        if [ "${SHELL_SELECTED[$i]}" = "1" ]; then
            IFS='|' read -r key _ _ <<< "${SHELLS[$i]}"
            SELECTED_SHELLS+=("$key")
        fi
    done

    if [ ${#SELECTED_SHELLS[@]} -eq 0 ]; then
        echo -e "  ${DIM}No shell agents selected — placeholder will use \$SHELL.${NC}"
        return
    fi

    echo -e "  ${GREEN}✓${NC} Shells: ${BOLD}${SELECTED_SHELLS[*]}${NC}"

    # Warn for shells that aren't installed on this host. Don't block — pre-staging
    # configs is a legitimate use case.
    for sh in "${SELECTED_SHELLS[@]}"; do
        if ! command -v "$sh" >/dev/null 2>&1; then
            echo -e "  ${YELLOW}⚠${NC} ${BOLD}$sh${NC} ${YELLOW}is not in PATH${NC} — install it on this host before spawning the agent."
        fi
    done

    # Append to SELECTED_AGENTS so configure_agent_selection
    # emit their TOML blocks. De-dup in case the user runs interactively twice.
    for sh in "${SELECTED_SHELLS[@]}"; do
        local already=0
        for a in "${SELECTED_AGENTS[@]}"; do
            [ "$a" = "$sh" ] && already=1 && break
        done
        [ $already -eq 0 ] && SELECTED_AGENTS+=("$sh")
    done
}

# Single-select default shell. Only invoked when ≥1 shell was chosen above.
# The chosen shell's absolute path is written into $DEFAULT_SHELL_BIN and used
# by do_install_dashboard to rewrite lince-viewport-placeholder's exec line.
select_default_shell() {
    if [ ${#SELECTED_SHELLS[@]} -eq 0 ]; then
        return
    fi

    echo ""
    print_separator
    echo -e "${BOLD}Step 3b: Default shell for the dashboard placeholder${NC}"
    echo ""
    echo -e "  ${DIM}The right-hand pane in the tiled layout (the ASCII-art one)${NC}"
    echo -e "  ${DIM}drops into a shell after the banner. Pick which one:${NC}"
    echo ""

    # Pre-select the host shell if it's in the chosen set, otherwise the first.
    local host_shell
    host_shell=$(basename "${SHELL:-/bin/bash}" 2>/dev/null)
    local default_idx=0
    for i in "${!SELECTED_SHELLS[@]}"; do
        if [ "${SELECTED_SHELLS[$i]}" = "$host_shell" ]; then
            default_idx=$i
            break
        fi
    done

    local idx=$default_idx
    while true; do
        for i in "${!SELECTED_SHELLS[@]}"; do
            local sh="${SELECTED_SHELLS[$i]}"
            if [ "$i" = "$idx" ]; then
                echo -e "  ${GREEN}(•)${NC} ${BOLD}$((i+1))) $sh${NC}"
            else
                echo -e "  ${DIM}( ) $((i+1))) $sh${NC}"
            fi
        done
        echo ""
        echo -e "  ${DIM}Press 1-${#SELECTED_SHELLS[@]} to pick, Enter to confirm${NC}"
        read -p "  > " -n 1 -r
        echo ""

        case "$REPLY" in
            [1-9])
                local pick=$((REPLY - 1))
                if [ $pick -lt ${#SELECTED_SHELLS[@]} ]; then
                    idx=$pick
                fi
                ;;
            "")
                break
                ;;
        esac

        redraw_up $(( ${#SELECTED_SHELLS[@]} + 3 ))
    done

    DEFAULT_SHELL="${SELECTED_SHELLS[$idx]}"
    # Resolve absolute path. If `command -v` fails (shell not installed),
    # leave DEFAULT_SHELL_BIN empty — do_install_dashboard skips the rewrite
    # so the placeholder keeps its current `exec "${SHELL:-/bin/bash}"` line.
    DEFAULT_SHELL_BIN=$(command -v "$DEFAULT_SHELL" 2>/dev/null || true)
    if [ -n "$DEFAULT_SHELL_BIN" ]; then
        echo -e "  ${GREEN}✓${NC} Default shell: ${BOLD}$DEFAULT_SHELL${NC} ${DIM}($DEFAULT_SHELL_BIN)${NC}"
    else
        echo -e "  ${YELLOW}⚠${NC} ${BOLD}$DEFAULT_SHELL${NC} ${YELLOW}not in PATH — placeholder will fall back to \$SHELL${NC}"
    fi
}

# ── TUI: VoxCode (voice input) ───────────────────────────────────────
select_voxcode() {
    echo ""
    print_separator
    echo -e "${BOLD}Step 4: Voice input (VoxCode)${NC}"
    echo ""
    echo -e "  VoxCode lets you speak to your agents — transcriptions are"
    echo -e "  routed to the focused agent via the dashboard."
    echo -e "  All audio processing happens locally (Whisper)."
    echo ""
    echo -e "  ${DIM}Requires: microphone, ~1GB disk (Whisper model), GPU recommended${NC}"
    echo -e "  ${DIM}Installed from: https://github.com/RisorseArtificiali/voxcode${NC}"
    echo ""

    if command -v voxcode >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ VoxCode already installed${NC}"
        INSTALL_VOXCODE=false
        return
    fi

    echo -e "  ${GREEN}1)${NC} ${BOLD}Yes${NC} — install VoxCode (voice input) ${GREEN}[default]${NC}"
    echo -e "  ${DIM}2)${NC} No  — skip for now (can install later)"
    echo ""
    read -p "  Choice [1]: " -n 1 -r
    echo ""

    case "${REPLY:-1}" in
        1|y|Y)
            # Check uv
            if ! command -v uv >/dev/null 2>&1; then
                echo ""
                echo -e "  ${YELLOW}VoxCode requires 'uv' (Python package manager).${NC}"
                echo -e "  ${DIM}Install with: curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
                echo ""
                if confirm "  Install uv now?"; then
                    curl -LsSf https://astral.sh/uv/install.sh | sh
                    export PATH="$HOME/.local/bin:$PATH"
                    if command -v uv >/dev/null 2>&1; then
                        echo -e "  ${GREEN}✓ uv installed${NC}"
                    else
                        echo -e "  ${RED}✗ uv installation failed. Skipping VoxCode.${NC}"
                        INSTALL_VOXCODE=false
                        return
                    fi
                else
                    echo -e "  ${YELLOW}Skipping VoxCode (uv required).${NC}"
                    INSTALL_VOXCODE=false
                    return
                fi
            fi
            INSTALL_VOXCODE=true
            echo -e "  ${GREEN}✓${NC} VoxCode will be installed"
            ;;
        *)
            INSTALL_VOXCODE=false
            echo -e "  ${DIM}Skipped. Install later: https://github.com/RisorseArtificiali/voxcode${NC}"
            ;;
    esac
}

# ── TUI: lince-lab (disposable lab VMs) ──────────────────────────────
#
# Optional, advanced. lince-lab gives an agent an isolated, disposable Linux VM
# (via Lima) to install/test things and git-bisect regressions without touching
# the host. The VM-control surface stays HOST-side: a broker (started on the host
# with `lince-lab lab broker start`) owns limactl/QEMU//dev/kvm; sandboxed agents
# reach it only through a unix socket — the sandbox is never given /dev/kvm.
# Linux-only in v1 (a macOS backend is planned, GH #268).
select_lince_lab() {
    echo ""
    print_separator
    echo -e "${BOLD}Step 5: Disposable lab VMs (lince-lab)${NC}"
    echo ""
    echo -e "  An agent can spin up an isolated, throwaway Linux VM to install and"
    echo -e "  test things — and git-bisect regressions — without touching your host."
    echo ""
    echo -e "  ${DIM}A host-side broker owns the VMs; agents drive it over a unix${NC}"
    echo -e "  ${DIM}socket. You start it on the host: 'lince-lab lab broker start'.${NC}"
    echo -e "  ${DIM}The sandbox is never given /dev/kvm.${NC}"
    echo ""
    echo -e "  ${DIM}To run VMs you'll need Lima + qemu-img + KVM (/dev/kvm).${NC}"
    echo ""

    if [ "$(uname -s)" = "Darwin" ]; then
        echo -e "  ${DIM}macOS detected — lince-lab v1 is Linux-only; skipping.${NC}"
        INSTALL_LINCE_LAB=false
        return
    fi
    if command -v lince-lab >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ lince-lab already installed${NC}"
        INSTALL_LINCE_LAB=false
        return
    fi

    echo -e "  ${DIM}1)${NC} Yes — install lince-lab"
    echo -e "  ${GREEN}2)${NC} ${BOLD}No${NC} — skip (install later) ${GREEN}[default]${NC}"
    echo ""
    read -p "  Choice [2]: " -n 1 -r
    echo ""
    case "${REPLY:-2}" in
        1|y|Y)
            INSTALL_LINCE_LAB=true
            echo -e "  ${GREEN}✓${NC} lince-lab will be installed"
            command -v limactl  >/dev/null 2>&1 || echo -e "  ${YELLOW}⚠${NC} limactl not found — install Lima to run VMs: ${DIM}https://lima-vm.io${NC}"
            command -v qemu-img >/dev/null 2>&1 || echo -e "  ${YELLOW}⚠${NC} qemu-img not found — ${DIM}sudo dnf install qemu-img qemu-kvm${NC}"
            [ -e /dev/kvm ] || echo -e "  ${YELLOW}⚠${NC} /dev/kvm not present — the broker host needs hardware virtualization (KVM)."
            ;;
        *)
            INSTALL_LINCE_LAB=false
            echo -e "  ${DIM}Skipped. Install later: lince-lab/install.sh${NC}"
            ;;
    esac
}

# ── TUI: Summary and confirm ────────────────────────────────────────
confirm_installation() {
    echo ""
    print_separator
    echo -e "${BOLD}Installation summary${NC}"
    echo ""

    if has_backend bwrap || has_backend seatbelt || has_backend nono; then
        echo -e "  ${GREEN}✓${NC} agent-sandbox    ${DIM}(secure isolation for agents)${NC}"
    fi
    echo -e "    Backends: ${BOLD}${SELECTED_BACKENDS[*]}${NC}"
    echo -e "    Levels:   ${BOLD}paranoid / normal / permissive${NC} ${DIM}(chosen per agent at spawn time)${NC}"

    echo -e "  ${GREEN}✓${NC} lince-dashboard  ${DIM}(multi-agent TUI)${NC}"
    echo -e "  ${GREEN}✓${NC} lince-config     ${DIM}(config CLI + lince-configure skill)${NC}"

    if [ "$INSTALL_VOXCODE" = true ]; then
        echo -e "  ${GREEN}✓${NC} voxcode          ${DIM}(voice input via Whisper)${NC}"
    fi
    if [ "$INSTALL_LINCE_LAB" = true ]; then
        echo -e "  ${GREEN}✓${NC} lince-lab        ${DIM}(disposable lab VMs — broker on host)${NC}"
    fi

    echo ""
    echo -e "  Agents:"
    for i in "${!AGENTS[@]}"; do
        IFS='|' read -r key name _ <<< "${AGENTS[$i]}"
        if [ "${AGENT_SELECTED[$i]}" = "1" ]; then
            local variants=""
            for b in "${SELECTED_BACKENDS[@]}"; do
                [ -n "$variants" ] && variants="$variants, "
                if [ "$b" = "unsandboxed" ]; then
                    variants="${variants}${RED}unsandboxed${NC}"
                else
                    variants="${variants}${GREEN}${b}${NC}"
                fi
            done
            echo -e "    ${GREEN}✓${NC} $name ${DIM}(${variants}${DIM})${NC}"
        fi
    done

    if [ ${#SELECTED_SHELLS[@]} -gt 0 ]; then
        echo ""
        echo -e "  Shells:"
        for sh in "${SELECTED_SHELLS[@]}"; do
            local marker=""
            if [ "$sh" = "$DEFAULT_SHELL" ]; then
                marker=" ${DIM}(default for tiled placeholder)${NC}"
            fi
            echo -e "    ${GREEN}✓${NC} $sh$marker"
        done
    fi

    echo ""
    if ! confirm "  Proceed with installation?"; then
        echo "  Cancelled."
        exit 2
    fi
}

# ── Install VoxCode ──────────────────────────────────────────────────
do_install_voxcode() {
    if [ "$INSTALL_VOXCODE" = false ]; then
        return
    fi

    echo ""
    print_separator
    echo -e "${BOLD}Installing VoxCode (voice input)...${NC}"
    echo ""

    local VOXCODE_DIR="$HOME/.local/share/voxcode"

    if [ -d "$VOXCODE_DIR" ]; then
        echo -e "  ${DIM}Removing previous clone...${NC}"
        rm -rf "$VOXCODE_DIR"
    fi
    echo -e "  ${DIM}Cloning voxcode...${NC}"
    git clone https://github.com/RisorseArtificiali/voxcode.git "$VOXCODE_DIR"

    cd "$VOXCODE_DIR"
    local voxcode_ok=false
    if bash install.sh; then
        echo -e "${GREEN}✓ VoxCode installed${NC}"
        voxcode_ok=true
    else
        echo -e "${RED}✗ VoxCode installation failed${NC}"
        echo -e "  ${DIM}Dashboard will use the standard layout (no voice pane).${NC}"
    fi

    # Clean up temporary clone
    cd "$SCRIPT_DIR"
    if [ "$voxcode_ok" = true ] && [ -d "$VOXCODE_DIR" ]; then
        echo -e "  ${DIM}Cleaning up voxcode clone...${NC}"
        rm -rf "$VOXCODE_DIR"
    fi
}

# ── Install lince-lab (optional, opt-in) ─────────────────────────────
do_install_lince_lab() {
    if [ "$INSTALL_LINCE_LAB" = false ]; then
        return
    fi

    echo ""
    print_separator
    echo -e "${BOLD}Installing lince-lab...${NC}"
    echo ""

    cd "$SCRIPT_DIR/lince-lab"
    if bash install.sh; then
        echo -e "${GREEN}✓ lince-lab installed${NC}"
        echo -e "  ${DIM}Start the broker on the host:${NC} ${CYAN}lince-lab lab broker start${NC}"
        echo -e "  ${DIM}Then run a recipe:${NC} ${CYAN}lince-lab run recipe <file>${NC}"
    else
        echo -e "${RED}✗ lince-lab installation failed${NC}"
        if ! confirm "Continue anyway?"; then exit 1; fi
    fi
    cd "$SCRIPT_DIR"
}

# ── Install sandbox ─────────────────────────────────────────────────
do_install_sandbox() {
    # Only install agent-sandbox if a sandboxed backend is selected
    if ! has_backend bwrap && ! has_backend seatbelt && ! has_backend nono; then
        return
    fi

    echo ""
    print_separator
    echo -e "${BOLD}Installing agent-sandbox...${NC}"
    echo ""

    cd "$SCRIPT_DIR/sandbox"
    if bash install.sh; then
        echo -e "${GREEN}✓ agent-sandbox installed${NC}"
    else
        echo -e "${RED}✗ agent-sandbox installation failed${NC}"
        if ! confirm "Continue anyway?"; then exit 1; fi
    fi

}

# ── Install lince-config CLI ────────────────────────────────────────
do_install_lince_config() {
    echo ""
    print_separator
    echo -e "${BOLD}Installing lince-config CLI...${NC}"
    echo ""

    cd "$SCRIPT_DIR/lince-config"
    if bash install.sh; then
        echo -e "${GREEN}✓ lince-config installed${NC}"
    else
        echo -e "${RED}✗ lince-config installation failed${NC}"
        echo -e "  ${DIM}The lince-configure skill will not be functional without it.${NC}"
        if ! confirm "Continue anyway?"; then exit 1; fi
    fi
}

# ── Agent selection → lince.toml (#207) ─────────────────────────────
#
# Selection used to be implemented by awk-filtering COPIES of the shipped
# agents-defaults files — installed files then differed from shipped ones in
# ways that were not user customization (#199/#204). Selection is now DATA:
# `lince-config apply <agent>+<level>` per picked agent plus
# [dashboard].enabled_agents in ~/.config/lince/lince.toml. The shipped
# registry/defaults stay complete; the dashboard picker reads the policy.
configure_agent_selection() {
    if [ ${#SELECTED_AGENTS[@]} -eq 0 ]; then
        return
    fi
    local LC="$HOME/.local/bin/lince-config"
    command -v lince-config >/dev/null 2>&1 && LC="lince-config"
    if ! "$LC" --version >/dev/null 2>&1; then
        echo -e "  ${YELLOW}⚠ lince-config unavailable — agent selection not persisted"
        echo -e "    (all registry agents will appear in the dashboard picker)${NC}"
        return
    fi

    echo ""
    echo -e "${CYAN}Persisting agent selection...${NC}"

    # enabled_agents restricts the New Agent wizard's picker to the selection
    # (absent = all registry agents).
    local json="["
    local first=true
    for agent in "${SELECTED_AGENTS[@]}"; do
        if [ "$first" = true ]; then first=false; else json="$json, "; fi
        json="$json\"$agent\""
    done
    json="$json]"

    # Creating ~/.config/lince/lince.toml switches resolution to v2-only (§5.2
    # hard switch). If unmigrated legacy customizations would be dropped (e.g.
    # [providers.*] in ~/.agent-sandbox/config.toml), `apply` refuses and asks
    # for --force-v2. Rather than force a lossy switch, persist the selection
    # into the legacy dashboard config — the resolver honors
    # [dashboard].enabled_agents in dual-read mode too (the v2 bridge).
    local probe_err
    probe_err="$("$LC" apply "${SELECTED_AGENTS[0]}+normal" --dry-run 2>&1 >/dev/null)"
    if echo "$probe_err" | grep -q -- "--force-v2"; then
        if "$LC" set dashboard.enabled_agents "$json" --target dashboard --quiet >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Agents enabled: ${SELECTED_AGENTS[*]}${NC} ${DIM}(legacy config — your providers are kept)${NC}"
        else
            echo -e "  ${YELLOW}⚠ Could not persist the agent selection — all registry"
            echo -e "    agents stay available in the dashboard picker.${NC}"
        fi
        return
    fi

    # No legacy blockers → write the v2 policy file.
    echo -e "  ${DIM}→ ~/.config/lince/lince.toml${NC}"
    local ok=true
    for agent in "${SELECTED_AGENTS[@]}"; do
        if ! "$LC" apply "${agent}+normal" >/dev/null 2>&1; then
            ok=false
        fi
    done
    if ! "$LC" set dashboard.enabled_agents "$json" --target lince --quiet >/dev/null 2>&1; then
        ok=false
    fi
    if [ "$ok" = true ]; then
        echo -e "${GREEN}✓ Agents enabled: ${SELECTED_AGENTS[*]}${NC}"
    else
        echo -e "  ${YELLOW}⚠ Could not fully persist the agent selection. All registry"
        echo -e "    agents stay available.${NC}"
    fi
}

# ── Install dashboard ───────────────────────────────────────────────
do_install_dashboard() {
    echo ""
    print_separator
    echo -e "${BOLD}Installing lince-dashboard...${NC}"
    echo ""

    cd "$SCRIPT_DIR/lince-dashboard"
    if bash install.sh; then
        echo -e "${GREEN}✓ lince-dashboard installed${NC}"
    else
        echo -e "${RED}✗ lince-dashboard installation failed${NC}"
        if ! confirm "Continue anyway?"; then exit 1; fi
    fi

    # Hardcode the chosen default shell into lince-viewport-placeholder.
    # The source ships with `exec "${SHELL:-/bin/bash}"` as a sentinel; we
    # rewrite that line to `exec "<absolute-path>"` so the tiled layout's
    # right-hand pane drops into the user-chosen shell instead of guessing
    # from $SHELL (which may differ between the install host and the user's
    # interactive sessions, e.g. when login=bash but interactive=zsh).
    if [ -n "$DEFAULT_SHELL_BIN" ]; then
        local placeholder="$HOME/.local/bin/lince-viewport-placeholder"
        if [ -f "$placeholder" ]; then
            # Match `exec "..."` lines — covers both the original
            # `exec "${SHELL:-/bin/bash}"` and any prior rewrite of ours,
            # so re-running quickstart with a different choice is idempotent.
            sed -i.bak -E "s|^exec \".*\"\$|exec \"$DEFAULT_SHELL_BIN\"|" "$placeholder"
            rm -f "${placeholder}.bak"
            echo -e "${GREEN}✓ Tiled placeholder shell: ${BOLD}$DEFAULT_SHELL${NC} ${DIM}($DEFAULT_SHELL_BIN)${NC}"
        fi
    fi
}

# ── Check prerequisites ─────────────────────────────────────────────
check_prerequisites() {
    echo -e "${BOLD}Checking prerequisites...${NC}"
    echo ""

    local warnings=()

    local OS_NAME
    OS_NAME="$(uname -s)"

    # Python
    if command -v python3 >/dev/null 2>&1; then
        local pyver
        pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo -e "  ${GREEN}✓${NC} Python $pyver"
    else
        warnings+=("Python 3.11+ not found")
        echo -e "  ${YELLOW}✗${NC} Python 3.11+ not found"
        if [ "$OS_NAME" = "Darwin" ]; then
            echo -e "      ${DIM}Install: brew install python@3.11${NC}"
        else
            echo -e "      ${DIM}# Fedora/RHEL: sudo dnf install python3.11${NC}"
            echo -e "      ${DIM}# Ubuntu/Debian: sudo apt install python3.11${NC}"
        fi
    fi

    # tomlkit (for lince-config CLI). Informational only — lince-config/install.sh
    # will pip-install it if missing.
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import tomlkit" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} python tomlkit"
        else
            echo -e "  ${YELLOW}✗${NC} python tomlkit — ${DIM}will be installed by lince-config${NC}"
        fi
    fi

    # Git
    if command -v git >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} git"
    else
        warnings+=("git not found")
        echo -e "  ${RED}✗${NC} git not found"
    fi

    # Zellij
    if command -v zellij >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} zellij $(zellij --version 2>/dev/null | awk '{print $2}')"
    else
        warnings+=("zellij not found (required for dashboard)")
        echo -e "  ${YELLOW}✗${NC} zellij not found — needed for dashboard"
    fi

    # Rustup (distro rustc alone cannot provide wasm32 targets needed for dashboard)
    if command -v rustup >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} rustup $(rustup --version 2>/dev/null | awk '{print $2}')"
        # On macOS, check for the common Homebrew Rust conflict: rustup binary
        # exists but the toolchain isn't set up, so cargo resolves to Homebrew's
        # standalone copy which can't see rustup-installed targets.
        if [ "$OS_NAME" = "Darwin" ] && ! rustup which cargo >/dev/null 2>&1; then
            echo -e "  ${YELLOW}⚠${NC} rustup found but no toolchain is active."
            echo -e "      ${DIM}Setting up default stable toolchain...${NC}"
            if rustup default stable 2>/dev/null; then
                # shellcheck disable=SC1090
                source "$HOME/.cargo/env" 2>/dev/null || true
                if rustup which cargo >/dev/null 2>&1; then
                    echo -e "  ${GREEN}✓${NC} rustup toolchain set up"
                else
                    warnings+=("rustup toolchain setup incomplete — dashboard build may fail")
                    echo -e "  ${YELLOW}✗${NC} toolchain setup did not complete. Try: rustup default stable"
                fi
            else
                warnings+=("rustup toolchain setup failed — dashboard build may fail")
                echo -e "  ${YELLOW}✗${NC} Could not set up toolchain. Run manually: rustup default stable"
            fi
        fi
    else
        warnings+=("rustup not found (required to build dashboard WASM plugin)")
        echo -e "  ${YELLOW}✗${NC} rustup not found — needed to build dashboard"
        echo -e "      ${DIM}Install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | RUSTUP_INIT_SKIP_PATH_CHECK=yes sh${NC}"
    fi

    # jq
    if command -v jq >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} jq"
    else
        warnings+=("jq not found")
        echo -e "  ${YELLOW}✗${NC} jq not found"
        if [ "$OS_NAME" = "Darwin" ]; then
            echo -e "      ${DIM}Install: brew install jq${NC}"
        else
            echo -e "      ${DIM}# Fedora/RHEL: sudo dnf install jq${NC}"
            echo -e "      ${DIM}# Ubuntu/Debian: sudo apt install jq${NC}"
        fi
    fi

    # Node.js
    if command -v node >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} node $(node --version 2>/dev/null)"
    else
        warnings+=("Node.js not found")
        echo -e "  ${YELLOW}✗${NC} node not found"
        if [ "$OS_NAME" = "Darwin" ]; then
            echo -e "      ${DIM}Install: brew install node${NC}"
        else
            echo -e "      ${DIM}# Fedora/RHEL: sudo dnf install nodejs${NC}"
            echo -e "      ${DIM}# Ubuntu/Debian: sudo apt install nodejs${NC}"
        fi
    fi

    # Sandbox backends
    if has_backend bwrap; then
        if command -v bwrap >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} bubblewrap"
        else
            warnings+=("bubblewrap not found")
            echo -e "  ${YELLOW}✗${NC} bubblewrap — ${DIM}install via your package manager (dnf/apt/pacman)${NC}"
        fi

        # Check unprivileged user namespaces (required by bubblewrap)
        local userns_ok=true
        local userns_clone
        userns_clone=$(sysctl -n kernel.unprivileged_userns_clone 2>/dev/null || true)
        if [ "$userns_clone" = "0" ]; then
            userns_ok=false
        fi
        # Ubuntu 24.04+ uses AppArmor as a second layer blocking user namespaces
        local apparmor_userns
        apparmor_userns=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || true)
        if [ "$apparmor_userns" = "1" ]; then
            userns_ok=false
        fi

        if [ "$userns_ok" = true ]; then
            echo -e "  ${GREEN}✓${NC} unprivileged user namespaces"
        else
            echo ""
            echo -e "  ${YELLOW}✗ Unprivileged user namespaces are restricted.${NC}"
            echo -e "  ${DIM}  bubblewrap needs them to create sandboxes.${NC}"
            echo ""
            if confirm "  Fix automatically? (requires sudo)"; then
                local sysctl_file="/etc/sysctl.d/50-bubblewrap.conf"
                {
                    echo "kernel.unprivileged_userns_clone=1"
                    echo "kernel.apparmor_restrict_unprivileged_userns=0"
                } | sudo tee "$sysctl_file" >/dev/null
                sudo sysctl --system >/dev/null 2>&1
                echo -e "  ${GREEN}✓ User namespaces enabled${NC}"
                echo -e "  ${DIM}  Persisted in $sysctl_file${NC}"
            else
                warnings+=("unprivileged user namespaces restricted — bwrap will fail")
                echo -e "  ${YELLOW}  To fix manually:${NC}"
                echo -e "  ${CYAN}  sudo sysctl kernel.unprivileged_userns_clone=1${NC}"
                echo -e "  ${CYAN}  sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0${NC}"
            fi
        fi
    fi
    if has_backend nono; then
        if command -v nono >/dev/null 2>&1; then
            echo -e "  ${YELLOW}✓${NC} nono (deprecated — consider Seatbelt if on macOS)"
        else
            warnings+=("nono not found")
            echo -e "  ${YELLOW}✗${NC} nono — ${DIM}deprecated; cargo install nono-cli${NC}"
        fi
    fi
    if has_backend seatbelt && [ "$(uname -s)" != "Darwin" ]; then
        warnings+=("seatbelt selected on a non-macOS host")
        echo -e "  ${RED}✗${NC} seatbelt — ${DIM}only available on macOS${NC}"
    fi

    if [ ${#warnings[@]} -gt 0 ]; then
        echo ""
        echo -e "  ${YELLOW}${#warnings[@]} warning(s). Install missing tools for full functionality.${NC}"
        if ! confirm "  Continue with installation?"; then
            exit 2
        fi
    fi
}

# ── Summary ──────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BLUE}${BOLD}════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}${BOLD}  Installation Complete${NC}"
    echo -e "${BLUE}${BOLD}════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "  ${GREEN}✓${NC} lince-dashboard"
    if has_backend bwrap; then
        echo -e "  ${GREEN}✓${NC} agent-sandbox (bwrap)"
    fi
    if has_backend seatbelt; then
        echo -e "  ${GREEN}✓${NC} agent-sandbox (seatbelt)"
    fi
    if has_backend nono; then
        echo -e "  ${YELLOW}✓${NC} agent-sandbox (nono, deprecated)"
    fi
    if has_backend unsandboxed; then
        echo -e "  ${RED}!${NC} unsandboxed mode"
    fi
    if [ -x "$HOME/.local/bin/lince-config" ]; then
        echo -e "  ${GREEN}✓${NC} lince-config CLI (powers /lince-configure)"
    fi
    if command -v voxcode >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} voxcode (voice input)"
    fi
    if [ "$INSTALL_LINCE_LAB" = true ]; then
        echo -e "  ${GREEN}✓${NC} lince-lab (disposable lab VMs)"
        echo -e "    ${DIM}Start the broker on the host: ${NC}${CYAN}lince-lab lab broker start${NC}"
    fi

    if [ ${#SELECTED_AGENTS[@]} -gt 0 ]; then
        echo ""
        echo -e "  Configured agents:"
        for agent in "${SELECTED_AGENTS[@]}"; do
            for entry in "${AGENTS[@]}"; do
                IFS='|' read -r key name _ <<< "$entry"
                if [ "$key" = "$agent" ]; then
                    echo -e "    ${GREEN}✓${NC} $name ${DIM}(${SELECTED_BACKENDS[*]})${NC}"
                    break
                fi
            done
        done
    fi

    echo ""
    echo -e "  ${BOLD}Get started:${NC}"
    echo ""
    echo -e "    ${CYAN}source ~/.bashrc${NC}"
    echo -e "    ${CYAN}lince${NC}            ${DIM}# tiled layout (default)${NC}"
    echo -e "    ${CYAN}lince-floating${NC}  ${DIM}# floating overlay layout${NC}"
    echo ""
    echo -e "  ${DIM}Press 'n' in the dashboard to spawn an agent.${NC}"
    echo -e "  ${DIM}Press '?' for the full keybindings help.${NC}"

    if ! command -v voxcode >/dev/null 2>&1; then
        echo ""
        echo -e "  ${YELLOW}Optional — Voice input:${NC}"
        echo -e "  ${DIM}https://github.com/RisorseArtificiali/voxcode${NC}"
    fi
    echo ""
}

# ── Parse arguments ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --defaults)
            USE_DEFAULTS=true
            shift
            ;;
        --help|-h)
            echo "LINCE Quickstart Installer"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --defaults   Install with defaults (all agents, bwrap sandbox)"
            echo "  --help       Show this help"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# ── Main ─────────────────────────────────────────────────────────────
print_banner

if [ "$USE_DEFAULTS" = true ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        SELECTED_BACKENDS=("seatbelt")  # bwrap is Linux-only; seatbelt is built into macOS
        echo -e "  ${DIM}Using defaults: all agents, seatbelt sandbox (macOS)${NC}"
    else
        SELECTED_BACKENDS=("bwrap")
    fi
    for i in "${!AGENTS[@]}"; do AGENT_SELECTED[$i]=1; done
    SELECTED_AGENTS=()
    for i in "${!AGENTS[@]}"; do
        IFS='|' read -r key _ _ <<< "${AGENTS[$i]}"
        SELECTED_AGENTS+=("$key")
    done
    # Ship the host's default shell as the only shell agent; everything else stays opt-in.
    DEFAULT_SHELL=$(basename "${SHELL:-/bin/bash}" 2>/dev/null)
    case "$DEFAULT_SHELL" in
        bash|zsh|fish) ;;
        *) DEFAULT_SHELL=bash ;;
    esac
    SELECTED_SHELLS=("$DEFAULT_SHELL")
    SELECTED_AGENTS+=("$DEFAULT_SHELL")
    DEFAULT_SHELL_BIN=$(command -v "$DEFAULT_SHELL" 2>/dev/null || true)
    echo -e "  ${DIM}Using defaults: all agents, $DEFAULT_SHELL shell, $([ "$(uname -s)" = "Darwin" ] && echo seatbelt || echo bwrap) sandbox${NC}"
else
    select_backends
    select_agents
    select_shells
    select_default_shell
    if [ "$(uname -s)" != "Darwin" ]; then
        select_voxcode
        select_lince_lab
    fi
    confirm_installation
fi

print_separator
check_prerequisites
print_separator

do_install_sandbox
do_install_voxcode        # before dashboard so step 14 detects voxcode
do_install_dashboard
do_install_lince_config   # CLI required by the lince-configure skill
do_install_lince_lab      # optional disposable-VM substrate (opt-in)
configure_agent_selection # selection becomes data in lince.toml (#207)
print_summary
