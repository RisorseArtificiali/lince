# Zellij Configuration Setup

Custom Zellij configuration with keybindings, predefined layouts for Claude Code (via `claude-sandbox`), and shell aliases.

## What's Included

### Main Configuration (`config.kdl`)
- Custom keybindings (Ctrl+O disabled for focus-mode compatibility)
- Dracula theme
- Copy-on-select enabled
- Scrollback buffer: 10000 lines
- Default layout: three-pane

### Layouts

All layouts share the same structure: a large pane on top (50%) running Claude Code in the sandbox, and two smaller panes below (25% each) for a backlog board and a free shell.

| Layout | Top pane command | Profile |
|--------|-----------------|---------|
| `three-pane` | `claude-sandbox run` | (default) |
| `three-pane-zai` | `claude-sandbox run -P zai` | Z.ai |
| `three-pane-mm` | `claude-sandbox run -P mm` | Minimax |
| `three-pane-vertex` | `claude-sandbox run -P vertex` | Vertex AI |

```
┌─────────────────────────────┐
│   claude-sandbox (50%)      │
├──────────────┬──────────────┤
│ backlog      │ shell        │
│ board (25%)  │ free  (25%)  │
└──────────────┴──────────────┘
```

### Aliases
```bash
z       # Start Zellij
z3      # Start with three-pane layout
zz3     # Start with three-pane-zai layout
zn      # Attach to existing session or create new
```

## Contents

```
zellij-setup/
├── install.sh              # Interactive installer
├── configs/
│   ├── config.kdl          # Main Zellij config
│   ├── three-pane.kdl      # Layout: default profile
│   ├── three-pane-zai.kdl  # Layout: Z.ai profile
│   ├── three-pane-mm.kdl   # Layout: Minimax profile
│   ├── three-pane-vertex.kdl # Layout: Vertex AI profile
│   └── zellij-aliases.sh   # Shell aliases
└── README.md
```

## Requirements

- **OS**: Fedora/RHEL (with dnf) — the script has comments for Ubuntu/Debian (apt-get)
- **Shell**: Bash or Zsh
- **Build deps** (if installing via Cargo): perl-IPC-Cmd, perl-core, openssl-devel
- **Optional**: `claude-sandbox`, `backlog` commands (used by layouts)

## Installation

```bash
cd zellij-setup
chmod +x install.sh
./install.sh
```

The script walks you through:

1. **Install Zellij** (if not present) — via dnf, cargo, or prebuilt binary
2. **Backup** existing configuration
3. **Create directories** (`~/.config/zellij/layouts/`)
4. **Copy config files** and verify syntax
5. **Check commands** used by layouts (`claude-sandbox`, `backlog`)
6. **Set up aliases** in `.bashrc` / `.zshrc`
7. **Test** that Zellij starts correctly

### Ubuntu/Debian

The installer defaults to `dnf`. On Debian-based systems, install build deps manually first:

```bash
sudo apt-get update
sudo apt-get install -y perl libssl-dev build-essential
./install.sh
```

## Usage

```bash
source ~/.bashrc   # reload aliases

z                  # plain Zellij
z3                 # three-pane (default profile)
zz3                # three-pane (zai profile)
zn                 # attach or create session
```

### Key Bindings

| Shortcut | Action |
|----------|--------|
| `Ctrl+g` | Locked mode (pass-through) |
| `Ctrl+p` | Pane mode |
| `Ctrl+t` | Tab mode |
| `Ctrl+n` | Resize mode |
| `Ctrl+h` | Move mode |
| `Ctrl+s` | Scroll mode |
| `Ctrl+q` | Quit |
| `Alt+arrows` | Navigate panes/tabs |
| `Alt+h/j/k/l` | Navigate (vim-style) |
| `Alt+n` | New pane |

**Note**: `Ctrl+O` is intentionally disabled for focus-mode compatibility.

### Session Management

```bash
zellij list-sessions              # list active sessions
zellij attach <name>              # attach to session
zellij -s <name>                  # create named session
zellij delete-session <name>      # kill session
zellij kill-all-sessions          # kill all
```

## Customization

### Modify Layouts

Layouts live in `~/.config/zellij/layouts/`. To change the top pane command:

```kdl
pane size="50%" {
    command "your-command"
    args "arg1" "arg2"
}
```

### Change Theme

In `~/.config/zellij/config.kdl`:

```kdl
theme "dracula"  // alternatives: "catppuccin-mocha", "tokyo-night", "gruvbox-dark"
```

## Troubleshooting

### "Can't locate IPC/Cmd.pm"

This happens during Cargo compilation:

```bash
# Fedora/RHEL
sudo dnf install -y perl-IPC-Cmd perl-core

# Ubuntu/Debian
sudo apt-get install -y perl
```

### Zellij won't start

```bash
zellij setup --check   # check config syntax
zellij --debug         # verbose logs
```

### Layout commands missing

If `claude-sandbox` or `backlog` aren't installed, the panes will show an error but Zellij still works. You can edit the layout to remove the command (the pane becomes a plain shell):

```kdl
# from:
pane size="50%" {
    command "claude-sandbox"
    args "run"
}

# to:
pane size="50%"
```

### Restore original config

```bash
ls -d ~/.config/zellij.backup.*              # list backups
rm -rf ~/.config/zellij
mv ~/.config/zellij.backup.TIMESTAMP ~/.config/zellij
```

## Uninstall

```bash
# remove config
rm -rf ~/.config/zellij

# remove aliases: edit ~/.bashrc and delete the "# Zellij aliases" block

# remove zellij
sudo dnf remove zellij          # or: cargo uninstall zellij
```

## Links

- [Zellij documentation](https://zellij.dev/documentation)
- [Keybindings reference](https://zellij.dev/documentation/keybindings)
- [Layouts reference](https://zellij.dev/documentation/layouts)
