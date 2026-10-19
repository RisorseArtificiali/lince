"""Strict global-only intake and path validation for opt-in mount masking.

Existing runner settings continue to use the legacy config loader.
"""

import re
import stat
import sys
import tomllib
from pathlib import Path


_ESSENTIAL_MOUNT_POINTS = frozenset(map(Path, ("/", "/proc", "/dev", "/run")))
_MOUNTINFO = Path("/proc/self/mountinfo")
_MOUNT_ESCAPE = re.compile(r"\\([0-7]{3})")


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
            if not (path.exists() or path.is_symlink()):
                continue
            key = f"[{table_name}].mask_mount_points"
            table = _table(_read(path, key), table_name, path)
            if "mask_mount_points" in table:
                raise MountMaskError(f"{label} config {path}: {key} is global-only")

    home = Path.home()
    v2_path = home / ".config/lince/lince.toml"
    if v2_path.exists() or v2_path.is_symlink():
        table = _read(v2_path, "[filesystem].mask_mount_points")
        _check_v2_version(table, v2_path)
        return _values(_table(table, "filesystem", v2_path), v2_path, "filesystem")

    legacy_path = home / ".agent-sandbox/config.toml"
    if legacy_path.exists() or legacy_path.is_symlink():
        return _values(_table(_read(legacy_path, "[sandbox].mask_mount_points"), "sandbox", legacy_path),
                       legacy_path, "sandbox")
    return ()


def _mounted_points() -> set[Path]:
    """Read exact mountpoints from this process's mount namespace, decoding mountinfo escapes."""
    try:
        lines = _MOUNTINFO.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise MountMaskError(f"cannot read {_MOUNTINFO} to check mounted paths: {exc}") from exc
    points = set()
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[4] == "":
            raise MountMaskError(f"invalid {_MOUNTINFO}: cannot determine mounted paths")
        decoded = _MOUNT_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), fields[4])
        points.add(Path(decoded))
    return points


def validate_mount_mask_points(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Validate without following links; order distinct points ancestor-first.

    A missing mountpoint is still masked: it may be a regular directory today
    and a mounted volume on a later launch.
    """
    if not paths:
        return ()
    validated = set()
    for raw in paths:
        if not raw.is_absolute() or "~" in raw.parts or ".." in raw.parts:
            raise MountMaskError(f"{raw}: mask mount point must be absolute, without ~ or ..")
        # Path collapses redundant separators and dots, but never dereferences links.
        point = Path("/", *raw.parts[1:])
        if point in _ESSENTIAL_MOUNT_POINTS:
            raise MountMaskError(f"{point}: cannot mask an essential mount point")
        current = Path("/")
        for component in point.parts[1:]:
            current = current / component
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError as exc:
                raise MountMaskError(f"{current}: mask mount point does not exist") from exc
            except OSError as exc:
                raise MountMaskError(f"{current}: cannot inspect mask mount point: {exc}") from exc
            if stat.S_ISLNK(mode):
                raise MountMaskError(f"{current}: mask mount point contains a symlink")
            if not stat.S_ISDIR(mode):
                raise MountMaskError(f"{current}: mask mount point is not a directory")
        if point in validated:
            raise MountMaskError(f"{point}: duplicate mask mount point")
        validated.add(point)

    mounted = _mounted_points()
    ordered = tuple(sorted(validated, key=lambda path: (len(path.parts), str(path))))
    for point in ordered:
        if point not in mounted:
            print(f"agent-sandbox: warning: {point}: path is not mounted at launch; "
                  "masking the path anyway", file=sys.stderr)
    return ordered
