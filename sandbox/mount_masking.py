"""Strict global-only intake and path validation for opt-in mount masking.

Existing runner settings continue to use the legacy config loader.
"""

import os
import re
import shlex
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
    home = Path.home()
    for label, root in (("invocation", invocation_dir), ("project", project_dir)):
        if label == "project" and project_dir == invocation_dir:
            continue
        for relative, table_name in ((".lince/lince.toml", "filesystem"),
                                      (".agent-sandbox/config.toml", "sandbox")):
            path = root / relative
            # The legacy global file also appears at the command root when
            # invoked from HOME (or an alias of HOME); it is not a local
            # override. Other local paths, even in the non-selected format,
            # still get checked below.
            if not (path.exists() or path.is_symlink()):
                continue
            if (relative == ".agent-sandbox/config.toml" and root.resolve() == home.resolve()
                    and path.resolve() == (home / relative).resolve()):
                continue
            key = f"[{table_name}].mask_mount_points"
            table = _table(_read(path, key), table_name, path)
            if "mask_mount_points" in table:
                raise MountMaskError(f"{label} config {path}: {key} is global-only")

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


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _dirs_between(parent: Path, child: Path) -> list[str]:
    """Make each component traversable after a parent tmpfs hides the tree."""
    result: list[str] = []
    current = parent
    for part in child.relative_to(parent).parts:
        current = current / part
        result += ["--dir", str(current)]
    return result


def mask_mount_args(paths: tuple[Path, ...], project_dir: Path) -> list[str]:
    """Plan ordered overlays and a persistent project bind for an opt-in run."""
    args: list[str] = []
    project = project_dir.resolve()
    for point in paths:
        parents = [previous for previous in paths if previous != point and _within(point, previous)]
        if parents:
            args += _dirs_between(parents[-1], point)
        args += ["--tmpfs", str(point)]

    parents = [point for point in paths if _within(project, point)]
    if parents:
        args += _dirs_between(parents[-1], project)
    args += ["--bind", str(project), str(project)]

    # A project bind also overlays masks inside that project. Reapply those
    # masks so the project remains writable without revealing those children.
    reapplied: list[Path] = []
    for point in paths:
        if point != project and _within(point, project):
            parents = [previous for previous in reapplied if _within(point, previous)]
            if parents:
                args += _dirs_between(parents[-1], point)
            args += ["--tmpfs", str(point)]
            reapplied.append(point)
    return args


_BIND_OPTIONS = frozenset(("--bind", "--ro-bind", "--dev-bind", "--bind-try",
                           "--ro-bind-try", "--dev-bind-try"))
_MOUNT_OPTIONS = frozenset(("--tmpfs", "--dev", "--proc", "--mqueue"))


def _host_path(value: str) -> Path:
    # bwrap binds use host sources, including paths reached through symlinks.
    # Resolve destinations conservatively too: a host symlink alias could
    # target a masked point, and refusing it is safer than overlooking it.
    try:
        return Path(value).resolve()
    except (OSError, RuntimeError) as exc:
        raise MountMaskError(f"{value}: cannot inspect automatic mount path: {exc}") from exc


def check_mount_exposures(argv: list[str], paths: tuple[Path, ...], project_dir: Path) -> None:
    """Fail closed if generated mounts reveal original content after masking.

    Call with the *final* bwrap argv, excluding explicit experimental raw args.
    Mount source paths refer to the host namespace, not the earlier overlays.
    """
    if not paths:
        return
    mounts: list[tuple[str, Path | None, Path]] = []
    i = 1
    while i < len(argv) and argv[i] != "--":
        option = argv[i]
        if option in _BIND_OPTIONS:
            if i + 2 >= len(argv):
                raise MountMaskError(f"incomplete bwrap mount option: {option}")
            mounts.append((option, _host_path(argv[i + 1]), _host_path(argv[i + 2])))
            i += 3
        elif option in _MOUNT_OPTIONS:
            if i + 1 >= len(argv):
                raise MountMaskError(f"incomplete bwrap mount option: {option}")
            mounts.append((option, None, _host_path(argv[i + 1])))
            i += 2
        elif option == "--setenv":
            i += 3
        elif option in ("--dir", "--unsetenv", "--chdir"):
            i += 2
        elif option in ("--symlink", "--file", "--bind-data"):
            i += 3
        else:
            i += 1

    project = project_dir.resolve()
    for point in paths:
        covering = [(option, src, dest) for option, src, dest in mounts if _within(point, dest)]
        if not covering:
            raise MountMaskError(f"{point}: missing mask mount in bwrap command")
        option, src, dest = covering[-1]
        if not (option == "--tmpfs" and dest == point or
                option == "--bind" and dest == project and point == project and src == project):
            raise MountMaskError(f"{point}: automatic mount at {dest} would re-expose a masked path; "
                                 "remove the overlapping mount or change mask_mount_points")

        for index, (option, src, dest) in enumerate(mounts):
            if src is None:
                continue
            if option == "--bind" and src == dest == project:
                continue
            if _within(src, point):
                # A subsequent tmpfs at the destination (or its ancestor)
                # completely obscures this exposure in the final namespace.
                if any(later == "--tmpfs" and _within(dest, target)
                       for later, _, target in mounts[index + 1:]):
                    continue
                raise MountMaskError(f"{src}: automatic {option} to {dest} would expose content from masked "
                                     f"{point}; remove the overlapping mount or change mask_mount_points")

            if _within(point, src):
                # Binding a parent maps the protected child to a *different*
                # location. Masking point itself cannot hide that alias.
                alias = dest / point.relative_to(src)
                covering = next(((later, later_src, target)
                                 for later, later_src, target in reversed(mounts[index + 1:])
                                 if _within(alias, target)), None)
                if covering:
                    later, later_src, target = covering
                    if later in _MOUNT_OPTIONS:
                        continue
                    if later in _BIND_OPTIONS:
                        mapped_child = _host_path(str(later_src / alias.relative_to(target)))
                        if (later == "--bind" and later_src == target == project or
                                not _within(mapped_child, point) and not _within(point, mapped_child)):
                            continue
                raise MountMaskError(f"{src}: automatic {option} to {dest} would expose masked "
                                     f"{point} at {alias}; add a later isolated overlay there or remove the bind")

    # Hooks need this always-generated host status bind. An opt-in tmpfs may
    # hide an earlier mount; a run with no reachable status directory is not
    # equivalent to a safely masked run.
    status = Path("/tmp/lince-dashboard")
    if any(_within(status, point) for point in paths):
        covering = [(option, src, dest) for option, src, dest in mounts if _within(status, dest)]
        if not covering or not (covering[-1] == ("--bind", status, status) or
                                covering[-1] == ("--bind", project, project)
                                and _within(status, project)):
            raise MountMaskError(f"{status}: mask_mount_points would hide the required status runtime bind; "
                                 "choose a narrower mask mount point")


def check_required_executables(argv: list[str], paths: tuple[Path, ...], project_dir: Path,
                               commands: tuple[str, ...]) -> None:
    """Check required exec paths in the final generated mount view, before spawning bwrap.

    Bind sources are host paths; the most recent mount covering an exec path
    determines whether that file survives the overlays. For a bare command,
    search the actual PATH passed to bwrap (not the host shell's PATH).
    """
    if not paths:
        return
    options = argv[:argv.index("--")]
    mounts: list[tuple[str, Path | None, Path]] = []
    sandbox_path = ""
    i = 1
    while i < len(options):
        option = options[i]
        if option in _BIND_OPTIONS:
            mounts.append((option, Path(options[i + 1]), Path(options[i + 2])))
            i += 3
        elif option in _MOUNT_OPTIONS:
            mounts.append((option, None, Path(options[i + 1])))
            i += 2
        elif option == "--setenv":
            if options[i + 1] == "PATH":
                sandbox_path = options[i + 2]
            i += 3
        elif option in ("--symlink", "--file", "--bind-data"):
            i += 3
        elif option in ("--dir", "--unsetenv", "--chdir"):
            i += 2
        else:
            i += 1

    def visible_executable(candidate: Path, visited: frozenset[Path] = frozenset()) -> Path | None:
        if candidate in visited:
            return None
        covering = next(((source, dest) for _, source, dest in reversed(mounts)
                         if _within(candidate, dest)), None)
        if covering is None or covering[0] is None:
            return None
        source, dest = covering
        mapped = source / candidate.relative_to(dest)
        if not mapped.is_file() or not os.access(mapped, os.X_OK):
            return None
        if mapped.is_symlink():
            link = mapped.readlink()
            target = link if link.is_absolute() else Path(os.path.normpath(str(candidate.parent / link)))
            return visible_executable(target, visited | {candidate})
        # A symlink in a parent component can likewise resolve into a mask,
        # unless a final bind replaced that parent with different content.
        resolved = candidate.resolve()
        if resolved != candidate and mapped == candidate:
            return visible_executable(resolved, visited | {candidate})
        return mapped

    pending = list(commands)
    checked: set[str] = set()
    while pending:
        command = pending.pop(0)
        if command in checked:
            continue
        checked.add(command)
        if "/" in command:
            candidate = Path(command)
            if not candidate.is_absolute():
                candidate = project_dir / candidate
            candidates = [candidate]
        else:
            candidates = [Path(directory or ".") / command for directory in sandbox_path.split(":")]

        def has_executable_source(candidate: Path) -> bool:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return True
            covering = next(((source, dest) for _, source, dest in reversed(mounts)
                             if _within(candidate, dest)), None)
            if covering is None or covering[0] is None:
                return False
            source, dest = covering
            mapped = source / candidate.relative_to(dest)
            return mapped.is_file() and os.access(mapped, os.X_OK)

        possible = [candidate for candidate in candidates if has_executable_source(candidate)]
        visible = next((source for candidate in possible if (source := visible_executable(candidate)) is not None),
                       None)
        if possible and visible is None:
            raise MountMaskError(f"{command}: mask_mount_points hides a required executable in the final "
                                 "sandbox view; move it into the project or choose a narrower mask mount point")
        if visible is not None:
            # An executable script also needs its kernel shebang interpreter.
            # Inspect the source that survives the final bind, not an earlier
            # host file shadowed at the same destination.
            try:
                with visible.open("rb") as stream:
                    first_line = stream.readline(256)
            except OSError:
                continue
            if first_line.startswith(b"#!"):
                try:
                    shebang = shlex.split(first_line[2:].decode("utf-8"))
                except (UnicodeError, ValueError):
                    continue
                if shebang:
                    pending.append(shebang[0])
                    if shebang[0] == "/usr/bin/env":
                        args = [arg for arg in shebang[1:] if not arg.startswith("-")]
                        if args:
                            pending.append(args[0])
