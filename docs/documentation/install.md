# Install and update LINCE

## Requirements

For the normal install you need:

- Linux: `curl`, `git`, and `bubblewrap` installed by your system package manager.
- macOS (experimental): `curl` and `git`. Seatbelt (`sandbox-exec`) is built in;
  Homebrew is not required.
- At least one coding agent you plan to use. Node and `jq` are optional.

The installer provisions Zellij 0.45.1 in `~/.local/bin` if the installed
version is missing or too old. It uses a system Python 3.11+ only when pip is
also available; otherwise it provisions pinned standalone Python 3.11.16 in
`~/.local/share/lince/python`. Existing compatible installations are reused.

WSL is not supported. The installer refuses it before provisioning or cloning
anything and points to [#356](https://github.com/RisorseArtificiali/lince/issues/356).

## One-line install

Interactive:

```bash
curl -sSL https://lince.sh/install | bash
```

Non-interactive, using the default agents, minimal status-line dashboard, and platform
sandbox:

```bash
curl -sSL https://lince.sh/install | bash -s -- --defaults
```

The bootstrap resolves the latest tagged release, checks out that exact tag in
a temporary `~/.local/share/lince/bootstrap-source` directory, delegates to the
module installers, and removes only that temporary checkout when successful.
Provisioned Python remains in `~/.local/share/lince/python`.

The default dashboard install downloads `lince-dashboard.wasm` and its
`SHA256SUMS` file from the same GitHub Release. It verifies the artifact with
`sha256sum` on Linux or `shasum -a 256` on macOS before replacing the installed
plugin. The pinned Zellij and standalone Python archives are also checked
against checksums embedded in the bootstrap.

## Manual install

Use the one-liner unless you need to inspect each step. From a tagged checkout,
with Zellij 0.45.1+, Python 3.11+ with pip, and the platform sandbox already
available:

```bash
git clone https://github.com/RisorseArtificiali/lince.git
cd lince
git checkout vX.Y.Z
LINCE_RELEASE_VERSION=vX.Y.Z ./quickstart.sh
```

Replace `vX.Y.Z` with a published release tag. Use `./quickstart.sh --defaults`
for a non-interactive install, keeping the same `LINCE_RELEASE_VERSION`
assignment. That variable makes the plugin installer fetch the artifact from
the same release as the checkout. Unlike the hosted bootstrap, `quickstart.sh`
does not provision Zellij or Python itself.

## Offline install

Prepare the machine before disconnecting. Copy these items from the same
release to removable media or an internal mirror:

- a checkout or source archive for the `vX.Y.Z` tag;
- `lince-dashboard.wasm` and `SHA256SUMS` from that release;
- any agent installers and Python packages you need (notably `tomlkit`).

The target must already have Zellij 0.45.1+, Python 3.11+ with pip and
`tomlkit`, plus `bubblewrap` on Linux. Then point the plugin installer at the
local directory while pinning the matching release:

```bash
cd /path/to/lince-vX.Y.Z
export LINCE_RELEASE_VERSION=vX.Y.Z
export LINCE_RELEASE_BASE_URL=file:///path/to/release-assets
./quickstart.sh --defaults
```

The local `SHA256SUMS` is still verified. The hosted one-liner itself is not an
offline installer: it needs GitHub to provision tools and fetch the release.

## Build from source

Building the dashboard locally is an explicit contributor path. Install
`rustup`, a C compiler/linker, and the WASI target first:

```bash
rustup target add wasm32-wasip1
curl -sSL https://lince.sh/install | bash -s -- --build-from-source
```

From an existing checkout, run `./quickstart.sh --build-from-source`. The
normal prebuilt install does not require Rust.

## Update

Check whether a newer release exists without changing the installation:

```bash
lince update --check
```

Update all installed modules from the latest tagged release:

```bash
lince update
```

The updater verifies the release plugin checksum, updates installed modules
through their idempotent `update.sh` scripts, preserves user configuration, and
records the new release version only after every module update succeeds.

## Manual release validation

Maintainers can use the [install validation checklist](install-validation-checklist.md)
for clean Linux and macOS smoke tests, idempotency, migration, and WSL refusal.
