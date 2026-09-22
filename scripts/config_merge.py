#!/usr/bin/env python3
"""config_merge.py -- Config-preserving TOML merge for LINCE update scripts (#108).

Merges newly shipped defaults into a user-owned TOML file:

  - the USER value wins on every conflict (scalars, arrays, inline values),
  - new default keys/tables are added recursively,
  - user-only (orphan) keys are preserved and listed on stdout,
  - comments and ordering of the user file are preserved (tomlkit),
  - a ``<user_file>.bak.<YYYYmmdd-HHMMSS>`` backup is created before any write,
  - ``--dry-run`` prints what would change without writing anything,
  - malformed input means NO write at all.

Usage:
    python3 scripts/config_merge.py <user_file> <defaults_file> [--dry-run]
        [--migrate <dotted.path> <old-value> <new-value>]

Exit codes:
    0  success (merged, or nothing to do)
    2  malformed/unreadable input -- nothing was written
    3  tomlkit is not installed -- nothing was written (caller should fall
       back to its previous preserve behaviour)

Environment variables are deliberately NOT consulted here: reset semantics
(LINCE_RESET_CONFIG) are the calling update.sh's responsibility.
"""

import argparse
import datetime
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

try:
    import tomlkit
except ImportError:
    print(
        "config_merge: the 'tomlkit' package is required but not installed.\n"
        "  Install it with: pip install --user tomlkit\n"
        "  (on Fedora/Debian system Pythons you may need:"
        " pip install --user --break-system-packages tomlkit)",
        file=sys.stderr,
    )
    sys.exit(3)


def _is_table(value: object) -> bool:
    """True for any TOML mapping (table, inline table, document)."""
    return isinstance(value, Mapping)


def merge_defaults(user: Mapping, defaults: Mapping, prefix: str = "") -> tuple[list[str], list[str]]:
    """Recursively add keys from ``defaults`` that are missing in ``user``.

    ``user`` is mutated in place. User values always win on conflicts; when
    both sides hold a table the merge recurses into it.

    Returns ``(added, orphans)`` -- dotted key paths that were added from the
    defaults, and dotted key paths present only in the user file (preserved).
    """
    added: list[str] = []
    orphans: list[str] = []
    for key, default_value in defaults.items():
        path = f"{prefix}{key}"
        if key not in user:
            user[key] = default_value
            added.append(path)
        else:
            user_value = user[key]
            if _is_table(user_value) and _is_table(default_value):
                sub_added, sub_orphans = merge_defaults(user_value, default_value, prefix=path + ".")
                added.extend(sub_added)
                orphans.extend(sub_orphans)
            # else: user wins -- keep the user's value untouched.
    for key in user.keys():
        if key not in defaults:
            orphans.append(f"{prefix}{key}")
    return added, orphans


def migrate_value(document: Mapping, dotted_path: str, old_value: str, new_value: str) -> bool:
    """Replace one exact scalar value at ``dotted_path`` while preserving TOML trivia."""
    parts = dotted_path.split(".")
    current = document
    for part in parts[:-1]:
        value = current.get(part)
        if not _is_table(value):
            return False
        current = value
    key = parts[-1]
    if current.get(key) != old_value:
        return False
    current[key] = new_value
    return True


def _unique_backup_path(path: Path) -> Path:
    """Return ``<name>.bak.<timestamp>`` that does not exist yet.

    Same-second reruns would otherwise silently overwrite the previous backup
    (shutil.copy2 clobbers); collisions get a ``-1``, ``-2``, ... suffix.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.bak.{timestamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak.{timestamp}-{counter}")
        counter += 1
    return candidate


def _load_doc(path: Path, label: str) -> tuple[str, "tomlkit.TOMLDocument"]:
    """Read and parse a TOML file. Raises SystemExit(2) with a clear message."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"config_merge: cannot read {label} file {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        return text, tomlkit.parse(text)
    except Exception as exc:  # tomlkit.exceptions.ParseError and friends
        print(f"config_merge: malformed TOML in {label} file {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="config_merge.py",
        description="Merge new shipped defaults into a user TOML file (user wins on conflicts).",
    )
    parser.add_argument("user_file", help="user-owned TOML file (merge destination)")
    parser.add_argument("defaults_file", help="newly shipped defaults TOML file")
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    parser.add_argument(
        "--migrate",
        nargs=3,
        action="append",
        default=[],
        metavar=("DOTTED_PATH", "OLD_VALUE", "NEW_VALUE"),
        help="replace an exact retired scalar value before merging defaults",
    )
    args = parser.parse_args(argv)

    user_path = Path(args.user_file)
    defaults_path = Path(args.defaults_file)

    try:
        _, defaults_doc = _load_doc(defaults_path, "defaults")
        user_exists = user_path.exists()
        if user_exists:
            user_text, user_doc = _load_doc(user_path, "user")
        else:
            user_text, user_doc = "", tomlkit.document()
    except SystemExit as exc:
        return int(exc.code or 2)

    migrated = []
    for dotted_path, old_value, new_value in args.migrate:
        if migrate_value(user_doc, dotted_path, old_value, new_value):
            migrated.append((dotted_path, old_value, new_value))
    added, orphans = merge_defaults(user_doc, defaults_doc)
    merged_text = tomlkit.dumps(user_doc)

    # The output must always round-trip through tomlkit.parse.
    try:
        tomlkit.parse(merged_text)
    except Exception as exc:
        print(f"config_merge: internal error -- merged output does not round-trip: {exc}", file=sys.stderr)
        return 2

    for path in added:
        print(f"added: {path}")
    for path in orphans:
        print(f"orphan (user-only, preserved): {path}")
    for path, old_value, new_value in migrated:
        print(f"migrated: {path}: {old_value} -> {new_value}")

    changed = (not user_exists) or merged_text != user_text

    if args.dry_run:
        if changed:
            print(f"dry-run: would write {user_path} ({len(added)} key(s) added)")
            if user_exists:
                print(f"dry-run: would back up {user_path} to {user_path.name}.bak.<timestamp> first")
        else:
            print(f"dry-run: no changes needed for {user_path}")
        return 0

    if not changed:
        print(f"no changes: {user_path} already up to date")
        return 0

    if user_exists:
        backup_path = _unique_backup_path(user_path)
        shutil.copy2(user_path, backup_path)
        print(f"backup: {backup_path}")

    user_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic swap: write to a sibling temp file then os.replace() so an
    # interrupted run can never leave a truncated config (the .bak above is the
    # recovery path, but the live file is never momentarily corrupt).
    tmp_path = user_path.with_name(f".{user_path.name}.tmp")
    tmp_path.write_text(merged_text, encoding="utf-8")
    os.replace(tmp_path, user_path)
    print(f"merged: {user_path} ({len(added)} key(s) added, {len(orphans)} user-only key(s) preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
