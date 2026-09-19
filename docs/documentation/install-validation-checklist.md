# Install validation checklist

Use a disposable machine or account for each clean-install scenario. Record the
OS, architecture, shell, release tag, and command output with the release
notes. These are manual release checks, not claims that every listed platform
was exercised by the current documentation change.

## Clean Linux

- [ ] Start with only `curl`, `git`, and distribution-provided `bubblewrap`;
  remove Zellij, Rust, and any Python 3.11+ interpreter from `PATH`.
- [ ] Run `curl -sSL https://lince.sh/install | bash -s -- --defaults`.
- [ ] Confirm Zellij is installed in `~/.local/bin`, standalone Python is in
  `~/.local/share/lince/python`, and the bootstrap clone was removed.
- [ ] Confirm the dashboard plugin was installed and its checksum verification
  succeeded, then launch `lince` and create an agent.
- [ ] Run `lince update --check` successfully.

## macOS without Homebrew

- [ ] Start from macOS with command-line `curl`, `git`, and built-in
  `sandbox-exec`, but without Homebrew, Zellij, or a compatible Python in
  `PATH`.
- [ ] Run `curl -sSL https://lince.sh/install | bash -s -- --defaults`.
- [ ] Confirm no Homebrew prompt or dependency appears, the pinned Zellij and
  standalone Python are provisioned, and Seatbelt is selected.
- [ ] Launch `lince`, create an agent, and run `lince update --check`.

## Idempotency

- [ ] On each clean-install machine, run the same `--defaults` one-liner a
  second time.
- [ ] Confirm compatible Zellij and Python are reused, user configuration is
  backed up before the selected default preset is applied, the dashboard still
  launches, and no stale `bootstrap-source` checkout remains.

## Migration from a source-built install

- [ ] Begin with an older LINCE checkout whose dashboard plugin was built from
  source and whose `lince` shell integration is active.
- [ ] Run the default one-liner without `--build-from-source`.
- [ ] Confirm the verified release plugin replaces the installed plugin, a
  backup is retained, prior configuration is available in the installer's
  timestamped backup, and `lince` launches without requiring Rust.
- [ ] Run `lince update --check`, followed by `lince update`, and launch again.

## WSL refusal

- [ ] Run the installer under real WSL before creating any LINCE directories.
- [ ] Confirm it exits non-zero with `WSL is not supported yet` and links to
  [#356](https://github.com/RisorseArtificiali/lince/issues/356).
- [ ] Confirm no Zellij/Python download or bootstrap checkout was created.
