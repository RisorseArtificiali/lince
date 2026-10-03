# Claude Code on Linux — Dev Guidelines

## Project Structure
- `sandbox/` — Bubblewrap sandbox for Claude Code (Python 3.11+, single-file script)
- `lince-dashboard/` — Multi-agent TUI dashboard (Zellij WASM plugin, Rust)
- `lince-config/` — Structured CLI for reading/editing LINCE TOML configs (also powers the `/lince-configure` skill)
- `registry.d/` — Unified agent registry: one TOML per shipped agent, consumed by sandbox + dashboard (shipped data, always overwritten on update; generated from the legacy agents-defaults files by `scripts/gen_registry.py` — edit those and regenerate)

## Build / Test
- **sandbox**: No build step. `python3 sandbox/agent-sandbox --help` to verify.
- **lince-dashboard**: `cd lince-dashboard/plugin && PATH="$HOME/.cargo/bin:$PATH" $HOME/.cargo/bin/cargo build --target wasm32-wasip1`

### Rust / WASM toolchain note
Fedora ships system `rustc`/`cargo` at `/usr/bin/` that **do not** include the `wasm32-wasip1` standard library. Always use the **rustup-managed** toolchain. You need BOTH `PATH` (so child `rustc` resolves correctly) AND the explicit `cargo` path:
```bash
PATH="$HOME/.cargo/bin:$PATH" $HOME/.cargo/bin/cargo build --target wasm32-wasip1
```
Or the build will fail with "can't find crate for `core`".

**IMPORTANT for Claude**: Never use bare `cargo` for WASM builds. The system cargo at `/usr/bin/cargo` invokes `/usr/bin/rustc` which lacks the wasm target. Always use the full command above — both PATH and explicit cargo path are required.

### WASI sandbox filesystem limitations
Zellij WASM plugins run inside a WASI sandbox with **restricted filesystem access**. `std::fs::read_to_string()` and similar direct I/O calls **silently fail** for paths outside the plugin's mapped directories (e.g. `~/.agent-sandbox/config.toml`).

**Rule**: All file I/O in the dashboard plugin must use `run_command()` (async shell commands via Zellij host) instead of `std::fs` calls. The result arrives in `Event::RunCommandResult` with a context map to identify the operation. See `state_file.rs` and `config.rs` `discover_profiles_async()` for the pattern.

## Installation Conventions

Every module must provide `install.sh`, `update.sh`, and `uninstall.sh` scripts.
- All file copies, config changes, and system modifications go through these scripts — never done manually or directly by Claude
- This applies to all modules: sandbox, lince-dashboard, and any future modules
- Scripts must be idempotent and safe to run multiple times
- The system must be installable by third parties from a clean clone

## Code Style
- Python: ruff defaults, line length 119
- Use absolute imports (never relative)
- Type hints where practical
- snake_case for functions/variables, CamelCase for classes
