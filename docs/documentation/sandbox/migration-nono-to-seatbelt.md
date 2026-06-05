# Migrating from nono to Seatbelt

The `nono` backend is **deprecated** in favor of the native macOS **Seatbelt** backend (`sandbox-exec`). Seatbelt is built into macOS at `/usr/bin/sandbox-exec` -- zero external dependencies required.

## Why migrate?

| Reason | Details |
|--------|---------|
| **Zero dependencies** | `sandbox-exec` ships with macOS. No `brew install` or `cargo install` needed. |
| **Full control** | Seatbelt profiles are plain `.sb` files you can inspect and edit. |
| **Better errors** | `sandbox-exec` reports denied operations with path and permission, making debugging straightforward. |
| **Active development** | The Seatbelt backend receives new features (sandbox levels, `extends` inheritance). nono integration is in maintenance mode. |
| **Feature parity** | All sandbox levels (`paranoid`, `normal`, `permissive`) and custom profiles work identically. |

## Quick migration steps

```bash
# 1. Generate Seatbelt profiles from your agent configuration
agent-sandbox seatbelt-sync

# 2. Verify the profiles were created
ls ~/.agent-sandbox/seatbelt-profiles/lince-*.sb

# 3. Test with an explicit backend selection
agent-sandbox run --backend seatbelt

# 4. Once confirmed working, update your config
# Edit ~/.agent-sandbox/config.toml:
#   [sandbox]
#   backend = "seatbelt"
# Or simply use "auto" — it prefers seatbelt on macOS.

# 5. (Optional) Uninstall nono
brew uninstall nono
```

## Profile comparison

| Aspect | nono | Seatbelt |
|--------|------|----------|
| Profile format | JSON (`.json`) | Scheme (`.sb`) |
| Profile location | `~/.config/nono/profiles/` | `~/.agent-sandbox/seatbelt-profiles/` |
| Generation command | `agent-sandbox nono-sync` | `agent-sandbox seatbelt-sync` |
| `extends` inheritance | No | Yes |
| Hand-editable | Yes (JSON) | Yes (plain text) |
| External dependency | Yes (`nono` binary) | No (`sandbox-exec` built-in) |

## Config changes

Only the `backend` value in `[sandbox]` changes:

```toml
# Before (deprecated)
[sandbox]
backend = "nono"

# After
[sandbox]
backend = "seatbelt"
# or simply:
backend = "auto"    # prefers seatbelt on macOS when sandbox-exec is available
```

No other configuration changes are needed. Agents, providers, sandbox levels, and all other settings remain identical.

## Feature parity notes

- **Sandbox levels**: `paranoid`, `normal`, and `permissive` work identically with both backends. Level-specific profiles are generated automatically by `seatbelt-sync`.
- **Providers / profiles**: Credential injection and provider switching work the same way.
- **Git push blocking**: Both backends block `git push` by default.
- **Custom profiles**: If you created custom nono profiles, you can create equivalent Seatbelt profiles using the `extends` inheritance feature. See [Configuration Reference](config-reference.md#sandbox-levels).

## Rollback

If you need to go back to nono temporarily:

```toml
[sandbox]
backend = "nono"
```

The nono backend remains functional -- it is deprecated, not removed. You will see a deprecation warning on stderr, but everything works as before.

## See also

- [Configuration Reference](config-reference.md) -- every TOML key documented
- [CLI Reference](cli-reference.md) -- `seatbelt-sync` command details
- [Epic #149](https://github.com/RisorseArtificiali/lince/issues/149) -- Seatbelt backend development tracker
