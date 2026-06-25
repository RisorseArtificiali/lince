"""User-friendly config + presets (blueprint §8).

Config is optional: sane defaults are baked into :data:`DEFAULTS` so a
non-expert can run ``lince-lab run recipe X`` with no config file. A user file
at ``$HOME/.config/lince-lab/config.toml`` overlays the defaults (read with
:mod:`tomllib`).

Three named presets (:data:`PRESETS`) set only resource / network / lifecycle
knobs. The **security invariants** — no host mounts, no host-credential
injection, VM name-prefixing — are *non-overridable policy*, not config keys, so
they deliberately do NOT appear in :data:`DEFAULTS` or any preset and cannot be
weakened through this layer.
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

# ── baked-in defaults (blueprint §8) ────────────────────────────────────────
# These are merged *under* a user config file. The image allowlist maps a short
# name to a pinned source so a recipe can only ask for a known image.
DEFAULTS: dict[str, Any] = {
    "socket_path": str(Path.home() / ".agent-sandbox" / "lince-lab.sock"),
    "grid_size": "80x24",
    # Image a bare `vm up <name>` (no recipe) boots; must key into `images` below.
    "default_image": "fedora",
    "vm": {
        "cpus": 2,
        "memory": "2GiB",
        "disk": "20GiB",
    },
    "network": {
        "mode": "deny",
    },
    # Pinned base images. Digests are SHA-256 of the qcow2, copied verbatim from
    # each distro's official CHECKSUM file (cross-checked against a 2nd mirror).
    # Fedora Cloud Base 44 (1.7), x86_64 — released 2026-04-28.
    #   CHECKSUM: https://download.fedoraproject.org/pub/fedora/linux/releases/44/Cloud/x86_64/images/Fedora-Cloud-44-1.7-x86_64-CHECKSUM
    #   verified via mirrors ftp.fau.de + mirror.init7.net (same digest).
    # Ubuntu 24.04 LTS (Noble) cloud image, amd64 — release dir [20260518].
    #   SHA256SUMS: https://cloud-images.ubuntu.com/releases/noble/release/SHA256SUMS
    "images": {
        "fedora": {
            "location": "https://download.fedoraproject.org/pub/fedora/linux/releases/44/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2",
            "arch": "x86_64",
            "digest": "sha256:28680fe5b371a5a82ebf43a31926e086a168e59949d03969c5093e7071f90b7f",
        },
        "ubuntu": {
            "location": "https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img",
            "arch": "x86_64",
            "digest": "sha256:53fdde898feed8b027d94baa9cfe8229867f330a1d9c49dc7d84465ee7f229f7",
        },
        # macOS guest for the Tart (Virtualization.framework) backend — Epic #268.
        # NOT a qcow2: the macOS backend reads `location` as a Tart OCI image ref
        # (`tart clone` pulls it). arch arm64 (Apple Silicon). Digest is handled by
        # the OCI registry, so none is pinned here.
        "macos-sequoia": {
            "location": "ghcr.io/cirruslabs/macos-sequoia-base:latest",
            "arch": "arm64",
            "digest": "",
        },
    },
}


# ── named presets (blueprint §8) ────────────────────────────────────────────
# Each preset only carries resource / network / lifecycle knobs. NO security
# invariant lives here — those are enforced in policy, not config.
PRESETS: dict[str, dict[str, Any]] = {
    "quick": {
        "description": (
            "Fast, minimal disposable VM for smoke-testing a single command or "
            "recipe. Auto-deleted, no base snapshot retained, network denied."
        ),
        "vm": {"cpus": 1, "memory": "1GiB", "disk": "10GiB"},
        "network": {"mode": "deny"},
        "keep_vm": False,
        "retain_base_snapshot": False,
        "step_timeout_s": 120,
    },
    "bisect": {
        "description": (
            "Tuned for the autonomous regression loop: base snapshot retained "
            "for fast per-candidate reset, network denied, longer per-step "
            "timeout. Use with `find bisect`."
        ),
        "vm": {"cpus": 2, "memory": "2GiB", "disk": "20GiB"},
        "network": {"mode": "deny"},
        "keep_vm": False,
        "retain_base_snapshot": True,
        "step_timeout_s": 600,
    },
    "networked": {
        "description": (
            "For recipes that legitimately must fetch (npm/pip). Network is "
            "allowed but ONLY the recipe's explicit allow_hosts/allow_ports; "
            "everything else stays denied and no host credentials are injected."
        ),
        "vm": {"cpus": 2, "memory": "2GiB", "disk": "20GiB"},
        "network": {"mode": "allow"},
        "keep_vm": False,
        "retain_base_snapshot": False,
        "step_timeout_s": 300,
    },
}


def default_config_path() -> Path:
    """Return the user config path, honoring ``$XDG_CONFIG_HOME`` then ``$HOME``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "lince-lab" / "config.toml"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: ``overlay`` merged recursively over ``base``.

    Nested dicts merge per-key; every other value (including lists) is replaced
    wholesale by the overlay. Neither input is mutated.
    """
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config, overlaying a user TOML file over :data:`DEFAULTS`.

    ``path`` defaults to :func:`default_config_path`. A missing file is not an
    error — the baked defaults are returned (config is optional). A malformed
    file falls back to the defaults rather than crashing a run; the resulting
    config is always a complete, usable dict.
    """
    cfg_path = path if path is not None else default_config_path()
    merged = copy.deepcopy(DEFAULTS)
    try:
        raw = cfg_path.read_bytes()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
        return merged
    try:
        user = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        # Sane fallback: a broken config file should not break every run.
        return merged
    if not isinstance(user, dict):
        return merged
    return _deep_merge(merged, user)


def apply_preset(config: dict[str, Any], preset: str) -> dict[str, Any]:
    """Return ``config`` with the named ``preset``'s knobs overlaid.

    Raises :class:`KeyError` for an unknown preset name. The preset's
    ``description`` is dropped from the merged result (it is documentation, not a
    runtime knob).
    """
    if preset not in PRESETS:
        raise KeyError(preset)
    knobs = {k: v for k, v in PRESETS[preset].items() if k != "description"}
    return _deep_merge(config, knobs)


def list_presets() -> list[dict[str, str]]:
    """Return ``[{"name", "description"}, ...]`` for the named presets.

    Stable ``name`` order so ``lince-lab run presets`` output is deterministic.
    """
    return [{"name": name, "description": PRESETS[name]["description"]} for name in sorted(PRESETS)]
