"""Strict, global-only intake for the opt-in mount masking policy.

This reads only the mask list; existing runner settings continue to use the
legacy config loader. Path and mount validation belong to the next step.
"""

import re
import tomllib
from pathlib import Path


class MountMaskError(ValueError):
    """The mount masking policy cannot be safely selected."""


def _read(path: Path, key: str) -> dict:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MountMaskError(f"{path}: invalid {key}: {exc}") from exc


def _table(document: dict, name: str, path: Path) -> dict:
    table = document.get(name, {})
    if not isinstance(table, dict):
        raise MountMaskError(f"{path}: [{name}].mask_mount_points: [{name}] must be a table")
    return table


def _check_v2_version(document: dict, path: Path) -> None:
    """Match lince-config's native 2.0 check_version_contract semantics."""
    version = document.get("version")
    label = f"{path}: [filesystem].mask_mount_points"
    if version is None:
        raise MountMaskError(f'{label}: missing required version; add version = "2.0"')
    match = re.fullmatch(r"(\d+)\.(\d+)", str(version))
    if match is None:
        raise MountMaskError(f'{label}: invalid version {version!r}; expected MAJOR.MINOR (e.g. "2.0")')
    major, minor = int(match.group(1)), int(match.group(2))
    if major != 2:
        raise MountMaskError(f"{label}: config schema {version} has a different major version than supported (2.0)")
    if minor > 0:
        raise MountMaskError(f"{label}: config written by a newer lince (schema {version} > native 2.0). "
                             "Run: lince update")


def _values(table: dict, path: Path, name: str) -> tuple[Path, ...]:
    values = table.get("mask_mount_points", [])
    label = f"{path}: [{name}].mask_mount_points"
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise MountMaskError(f"{label}: expected a list of directory path strings")
    return tuple(Path(value) for value in values)


def load_mount_mask_points(invocation_dir: Path, project_dir: Path) -> tuple[Path, ...]:
    """Read the global mask list after rejecting any local definition.

    File *presence*, not list truthiness, chooses Config v2. Both local
    formats are checked at each distinct command root, independently of the
    format chosen globally and independently of the runner's legacy merge.
    """
    for label, root in (("invocation", invocation_dir), ("project", project_dir)):
        if label == "project" and project_dir == invocation_dir:
            continue
        for relative, table_name in ((".lince/lince.toml", "filesystem"),
                                     (".agent-sandbox/config.toml", "sandbox")):
            path = root / relative
            if not path.exists():
                continue
            key = f"[{table_name}].mask_mount_points"
            table = _table(_read(path, key), table_name, path)
            if "mask_mount_points" in table:
                raise MountMaskError(f"{label} config {path}: {key} is global-only")

    home = Path.home()
    v2_path = home / ".config/lince/lince.toml"
    if v2_path.exists():
        table = _read(v2_path, "[filesystem].mask_mount_points")
        _check_v2_version(table, v2_path)
        return _values(_table(table, "filesystem", v2_path), v2_path, "filesystem")

    legacy_path = home / ".agent-sandbox/config.toml"
    if legacy_path.exists():
        return _values(_table(_read(legacy_path, "[sandbox].mask_mount_points"), "sandbox", legacy_path),
                       legacy_path, "sandbox")
    return ()
