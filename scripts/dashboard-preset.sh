#!/usr/bin/env bash
# Shared by quickstart and the standalone dashboard installer.
select_dashboard_preset() {
    local choice
    if [ -n "${LINCE_DASHBOARD_PRESET:-}" ]; then
        case "$LINCE_DASHBOARD_PRESET" in
            minimal|side-pane|classic) return 0 ;;
            *) echo "Invalid LINCE_DASHBOARD_PRESET: $LINCE_DASHBOARD_PRESET" >&2; return 1 ;;
        esac
    fi
    echo ""
    echo "Choose your dashboard preset:"
    echo "  1) minimal (default) — LINCE status bar only; sidebar initially hidden (Alt+s to show it)."
    echo "  2) side-pane — compact sidebar and LINCE status bar; more space for agents."
    echo "  3) classic — full agent table with standard Zellij bars."
    echo "  Documentation: https://lince.sh/documentation/#/dashboard/views-and-themes"
    while true; do
        read -r -p "  Preset [1]: " choice || choice=""
        case "$choice" in
            ""|1|minimal) LINCE_DASHBOARD_PRESET=minimal; break ;;
            2|side-pane) LINCE_DASHBOARD_PRESET=side-pane; break ;;
            3|classic) LINCE_DASHBOARD_PRESET=classic; break ;;
            *) echo "  Choose 1, 2 or 3 (or the preset name)." ;;
        esac
    done
    echo "  Dashboard preset: $LINCE_DASHBOARD_PRESET"
}

# Source is the shipped template; install.sh handles backups before calling this.
write_dashboard_preset_config() {
    case "${LINCE_DASHBOARD_PRESET:-minimal}" in
        minimal|side-pane|classic) ;;
        *) echo "Invalid dashboard preset" >&2; return 1 ;;
    esac
    sed "s/^preset = \"minimal\"$/preset = \"${LINCE_DASHBOARD_PRESET:-minimal}\"/" "$1" > "$2"
}
