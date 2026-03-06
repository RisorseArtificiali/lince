# VoxCode

Voice input for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) on Linux. Speak into your microphone and your words get transcribed locally (via Whisper) and sent as prompts to Claude Code.

All processing happens on your machine — no audio data leaves your computer.

## How it works

```
You speak → Microphone → Whisper (local, GPU) → Text → tmux/Zellij → Claude Code
```

VoxCode runs in a terminal multiplexer pane (tmux or Zellij) next to Claude Code. You speak, VoxCode transcribes your words into a text buffer. When you say **"comando: invia"** (or press Enter), the text is sent to Claude Code as if you typed it.

## Prerequisites

Before installing VoxCode, make sure you have:

1. **Linux** (tested on Fedora 43, should work on Ubuntu/Debian)
2. **A working microphone** (built-in laptop mic is fine)
3. **NVIDIA GPU with proprietary drivers** (recommended) or CPU-only (much slower)
4. **Claude Code** installed and working

### Check your prerequisites

```bash
# Check NVIDIA GPU and drivers (skip if using CPU-only)
nvidia-smi
# You should see your GPU model and driver version

# Check microphone (should list at least one input device)
arecord -l
# Or: pactl list sources short

# Check Claude Code is installed
claude --version
```

### Install Claude Code (if you don't have it)

```bash
# Claude Code requires Node.js 18+
# Install Node.js first if needed:
#   Fedora: sudo dnf install nodejs
#   Ubuntu: sudo apt install nodejs npm

npm install -g @anthropic-ai/claude-code
```

## Installation

### Step 1: Install system packages

**Fedora / RHEL / Rocky:**

```bash
sudo dnf install tmux pipewire pipewire-pulseaudio portaudio-devel   # or: zellij instead of tmux
```

**Ubuntu / Debian:**

```bash
sudo apt install tmux libportaudio2 pipewire pipewire-pulse    # or: zellij instead of tmux
```

### Step 2: Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen your terminal after installing uv, or run `source ~/.bashrc`.

### Step 3: Download and install VoxCode

```bash
git clone <repo-url>
cd voxcode
uv sync
```

`uv sync` downloads Python (if needed) and all dependencies. This takes about a minute.

### Step 4: Test your microphone

Run this before anything else to make sure audio capture and transcription work:

```bash
uv run python test_interactive.py --devices
```

You should see a list of audio devices with your microphone marked as default input. Look for your microphone in the list and note the **device number** (the number at the beginning of each line, e.g., `> 13`).

**If your microphone is NOT the default device** (common with external USB microphones), you need to specify the device number. For example, if your USB mic is device 13:

```bash
uv run python test_interactive.py --audio-device 13
```

If the default device is correct, just run it without `--audio-device`.

Now test actual transcription — **speak into your microphone when you see "Speak now!"**:

```bash
uv run python test_interactive.py
# Or with a specific device:
uv run python test_interactive.py --audio-device 13
```

What you should see:

```
╭──────────────────────────────────────╮
│     VoxCode Interactive Audio Test   │
╰──────────────────────────────────────╯

  Model: large-v3 on cuda (float16)
  Language: auto
  Mode: VAD (continuous) — speak naturally, pauses trigger transcription

  Loading Whisper model...          ← first run downloads ~3 GB, takes a few minutes
  Model loaded.
  Capture: 48000Hz → 16kHz resampled

  Speak now! Say 'comando: invia' to test voice commands.
  Press Ctrl+C to stop.

  ● listening  ███░░░░░░░░░░░░░░░░░░░░░░ 0.0012    ← silence, low level
  ● REC        ██████████████░░░░░░░░░░░░ 0.0847    ← you're speaking!
  [1] Hello, this is a test (en, 0.8s)               ← transcribed text
```

If this works, your audio pipeline is ready. Press `Ctrl+C` to stop.

**Troubleshooting the test:**
- If audio level stays near 0.0000 even when speaking: you're using the wrong audio device. Run `--devices` and try a different device number with `--audio-device N`
- If the model is too slow or you don't have a GPU: `uv run python test_interactive.py --model small --device cpu --compute-type int8`
- If you prefer press-to-talk instead of continuous listening: `uv run python test_interactive.py --ptt`

## Using VoxCode with Claude Code

### Quick start (recommended)

A single command sets up everything — a multiplexer session with Claude Code and VoxCode side by side:

```bash
uv run voxcode --launch              # auto-detects tmux or Zellij
uv run voxcode --launch --backend tmux     # force tmux
uv run voxcode --launch --backend zellij   # force Zellij
```

This creates a session called `voxcode` with two panes:

```
┌──────────────────────┬──────────────────────┐
│                      │                      │
│    Claude Code       │    VoxCode           │
│    waiting for       │    ● LISTENING       │
│    your input...     │                      │
│                      │                      │
└──────────────────────┴──────────────────────┘
```

You can also launch a different command in the first pane:

```bash
uv run voxcode --launch "claude --model opus"
uv run voxcode --launch vim
```

The default command is `claude`, configurable in `config.toml`:

```toml
[multiplexer]
launch_command = "claude"
```

If the session already exists, `--launch` reattaches to it.

By default, VoxCode injects text **without pressing Enter** — you review it in the Claude Code pane and press Enter when ready. To send automatically:

```toml
[multiplexer]
send_enter = true
```

### Manual setup

If you prefer to set up the tmux panes yourself:

**1. Open a terminal and start tmux:**

```bash
tmux
```

Your terminal is now inside tmux (you'll see a green bar at the bottom).

**2. Start Claude Code:**

```bash
claude
```

Claude Code starts in this pane. You should see its prompt waiting for input.

**3. Create a second pane for VoxCode:**

Press `Ctrl+B`, then `%` (percent sign). This splits your terminal into two panes side by side.

Your cursor is now in the right pane.

**4. Start VoxCode in the new pane:**

```bash
cd ~/path/to/voxcode
uv run voxcode
```

Replace `~/path/to/voxcode` with wherever you cloned the project (e.g., `cd ~/voxcode`).

VoxCode auto-detects the Claude Code pane. You should see:

```
╭────────────── VoxCode ──────────────╮
│ Mode:    VAD  ● LISTENING           │
│ Level:   ███░░░░░░░░░░░░░░░░░░░░░░ │
│ Pane:    0:0.0                      │
│ Keys:    [Enter] send  [c] clear    │
│          [q] quit                   │
╰─────────────────────────────────────╯
```

**5. Speak and send your first voice command:**

Say something, for example: *"explain what the ls command does"*

You'll see the status change to `● RECORDING` while you speak, then `● TRANSCRIBING`, and then your text appears in the Buffer line:

```
│ Buffer:  explain what the ls command does │
```

Now **send it to Claude Code** in one of two ways:
- **Voice:** Say **"comando: invia"**
- **Keyboard:** Press **Enter**

The text disappears from the buffer and appears in the Claude Code pane as if you typed it. Claude Code processes it and responds.

```
│ Sent:    explain what the ls command does │
│ Buffer:                                   │
```

That's it! You're now controlling Claude Code with your voice.

### The voice workflow

```
  speak         speak more      "comando: invia"     Claude Code
  "explain"  →  "the ls"     →  (or press Enter)  →  receives the
  "what..."     "command does"                        full prompt
     │              │                   │
     ▼              ▼                   ▼
  Buffer:       Buffer: explain      Buffer is sent,
  "explain      what the ls          cleared, ready
   what..."     command does"        for next prompt
```

Key points:
- **Text accumulates** in the buffer as you speak. Multiple speech segments are joined together.
- **Nothing is sent** until you explicitly say "comando: invia" or press Enter.
- **Say "comando: cancella"** (or press `c`) to clear the buffer and start over.
- **Say "comando: pausa"** to temporarily stop listening (say "comando: riprendi" to resume).

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Enter` | Send buffer to Claude Code |
| `c` | Clear buffer |
| `q` | Quit VoxCode |
| `Ctrl+C` | Quit VoxCode |
| `Space` | Toggle recording (PTT mode only) |

### Voice commands

Voice commands must start with the prefix **"comando:"** so VoxCode can tell them apart from regular speech.

| Say this | What happens |
|---|---|
| "comando: invia" or "comando: send" | Send buffer to Claude Code |
| "comando: cancella" or "comando: cancel" | Clear the buffer |
| "comando: pausa" or "comando: pause" | Pause listening |
| "comando: riprendi" or "comando: resume" | Resume listening |

Both Italian and English command words work regardless of what language you're speaking.

## tmux cheat sheet

If you've never used tmux before, here's everything you need:

| What you want to do | What to press |
|---|---|
| Start tmux | Type `tmux` and press Enter |
| Split into two panes (side by side) | `Ctrl+B` then `%` |
| Split into two panes (top/bottom) | `Ctrl+B` then `"` |
| Move to the other pane | `Ctrl+B` then arrow key (← or →) |
| Close a pane | Type `exit` or press `Ctrl+D` |
| Detach from tmux (it keeps running) | `Ctrl+B` then `d` |
| Reattach to a running tmux session | Type `tmux attach` |

**Important:** In tmux, `Ctrl+B` is the "prefix key". You press it, release it, then press the next key. Don't hold them all at once.

## Input modes

**VAD mode (default)** — VoxCode listens continuously. When you speak, it starts recording. When you stop speaking for ~1.5 seconds, it transcribes. This is the "hands-free" mode.

```bash
uv run voxcode              # VAD mode
```

**PTT mode (push-to-talk)** — Press Space to start recording, Space again to stop. Useful in noisy environments where VAD might trigger on background noise.

```bash
uv run voxcode --mode ptt   # PTT mode
```

## Configuration

VoxCode works with sensible defaults. You only need a config file if you want to change something.

```bash
cp config.example.toml config.toml
# Edit config.toml with your preferred text editor
```

VoxCode looks for config in this order:
1. `./config.toml` (current directory)
2. `~/.config/voxcode/config.toml`
3. Built-in defaults

### Common settings to change

**Send automatically without confirmation:**

```toml
[general]
auto_send = true    # sends text to Claude Code as soon as you stop speaking
```

**Use a smaller/faster model:**

```toml
[whisper]
model = "small"     # much faster, less accurate
```

**CPU-only (no NVIDIA GPU):**

```toml
[whisper]
device = "cpu"
compute_type = "int8" # consider using "float32" for higher precision (slower)
model = "small"     # large models are too slow on CPU
```

**Adjust speech detection sensitivity:**

```toml
[vad]
threshold = 0.01    # lower = more sensitive (picks up quieter speech)
threshold = 0.03    # higher = less sensitive (ignores background noise)
```

**Use a specific microphone** (if the default input device isn't your mic):

```toml
[audio]
device = 13    # find yours with: uv run voxcode --list-devices
```

**Set tmux pane manually** (if auto-detect doesn't find Claude Code):

```toml
[tmux]
auto_detect = false
target_pane = "0:0.0"   # find yours with: tmux list-panes -a
```

**Disable voice commands** (if "comando:" triggers too often by accident):

```toml
[commands]
enabled = false
```

### Whisper model comparison

| Model | VRAM needed | Speed | Accuracy | Recommended for |
|---|---|---|---|---|
| `tiny` | ~1 GB | Instant | Low | Quick testing only |
| `base` | ~1 GB | Very fast | Fair | Low-end hardware |
| `small` | ~2 GB | Fast | Good | CPU-only or limited VRAM |
| `medium` | ~5 GB | Medium | Very good | Balanced choice |
| `large-v3` | ~10 GB | ~1-2s | Best | Default, best accuracy |

### CLI options

Override config settings without editing the file:

```bash
uv run voxcode --launch                # Launch tmux/Zellij with Claude Code + VoxCode
uv run voxcode --launch "vim"          # Launch with a custom command + VoxCode
uv run voxcode --backend zellij        # Force Zellij backend
uv run voxcode --backend tmux          # Force tmux backend
uv run voxcode --mode ptt              # Push-to-talk
uv run voxcode --model small           # Smaller model
uv run voxcode --device cpu            # CPU-only
uv run voxcode --language it           # Force Italian
uv run voxcode --audio-device 13       # Use specific microphone (see --list-devices)
uv run voxcode --config myconfig.toml  # Custom config file
uv run voxcode --list-devices          # Show audio devices
```

## Troubleshooting

### VoxCode says "Could not find Claude Code pane"

VoxCode looks for a multiplexer pane running a process with "claude" in the name.

**Fix 1:** Make sure Claude Code is actually running in a multiplexer pane (not in a separate terminal outside tmux/Zellij).

**Fix 2 (tmux):** Check what tmux sees:
```bash
tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command}"
```

**Fix 2 (Zellij):** Check what Zellij sees:
```bash
zellij list-sessions
```

**Fix 3:** Set the pane manually in `config.toml`:

For tmux:
```toml
[tmux]
auto_detect = false
target_pane = "0:0.0"    # replace with your pane from the command above
```

For Zellij:
```toml
[zellij]
auto_detect = false
target_pane = "next"     # "next" or "previous" relative to VoxCode pane
```

### No audio / microphone not detected

```bash
# Check devices
uv run python test_interactive.py --devices

# Make sure PipeWire/PulseAudio is running
pactl info | head -5

# Test recording with system tools
arecord -d 3 -f cd test.wav && aplay test.wav
```

### Transcription is slow or inaccurate

```bash
# Verify GPU is being used
nvidia-smi
# Look for a python process using VRAM

# Switch to a smaller model
uv run voxcode --model small

# Or try int8 quantization (less VRAM, similar quality to float16)
# In config.toml: compute_type = "int8"
```

### First run is very slow

The first run downloads the Whisper model from HuggingFace (~3 GB for large-v3). Subsequent runs load it from cache (~5-10 seconds).

If the download fails:
```bash
# Models are cached here:
ls ~/.cache/huggingface/hub/models--Systran--faster-whisper-*

# Delete and retry if corrupted
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-*
```

### VoxCode picks up too much background noise

Increase the VAD threshold in `config.toml`:
```toml
[vad]
threshold = 0.03    # default is 0.015, higher = less sensitive
```

Or switch to PTT mode to avoid false triggers:
```bash
uv run voxcode --mode ptt
```

## Project structure

```
voxcode/
├── pyproject.toml           # Project config and dependencies
├── config.example.toml      # Example configuration
├── test_interactive.py      # Interactive audio test (no tmux needed)
├── README.md                # This file
├── ROADMAP.md               # Future features and extension plans
└── src/voxcode/
    ├── __init__.py           # Package marker
    ├── __main__.py           # Allows `python -m voxcode`
    ├── cli.py               # Main app loop and orchestration
    ├── config.py             # TOML config loading
    ├── audio.py              # Microphone capture with resampling
    ├── vad.py                # Voice activity detection
    ├── transcriber.py        # Whisper transcription wrapper
    ├── commands.py           # Voice command parser
    ├── multiplexer.py        # Multiplexer abstraction and auto-detection
    ├── tmux_bridge.py        # tmux backend
    ├── zellij_bridge.py      # Zellij backend
    └── ui.py                 # Terminal UI (rich)
```
