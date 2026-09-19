import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
QUICKSTART_PATH = ROOT / "quickstart.sh"
DASHBOARD_INSTALL = ROOT / "lince-dashboard/install.sh"


def shell_function(source: str, name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing shell function: {name}"
    return match.group(0)


def run_dashboard_handoff(build_from_source: bool) -> str:
    quickstart = QUICKSTART_PATH.read_text()
    function = shell_function(quickstart, "do_install_dashboard")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dashboard = root / "lince-dashboard"
        dashboard.mkdir()
        log = root / "args"
        installer = dashboard / "install.sh"
        installer.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > "{log}"\n')
        installer.chmod(0o755)
        script = f"""
SCRIPT_DIR={root!s}
BUILD_FROM_SOURCE={'true' if build_from_source else 'false'}
LINCE_DASHBOARD_PRESET=minimal
DEFAULT_SHELL_BIN=
RED= GREEN= BOLD= DIM= NC=
print_separator() {{ :; }}
confirm() {{ return 1; }}
{function}
do_install_dashboard
"""
        result = subprocess.run(
            ["/bin/bash", "-c", script],
            env=os.environ,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return log.read_text().strip()


def run_quickstart_prerequisites(build_from_source: bool) -> subprocess.CompletedProcess[str]:
    function = shell_function(QUICKSTART_PATH.read_text(), "check_prerequisites")
    script = f"""
RED= GREEN= YELLOW= BOLD= DIM= NC=
BUILD_FROM_SOURCE={'true' if build_from_source else 'false'}
check_zellij_version() {{ return 0; }}
has_backend() {{ return 1; }}
confirm() {{ echo confirm-called; return 1; }}
{function}
check_prerequisites
"""
    return subprocess.run(
        ["/bin/bash", "-c", script],
        env={**os.environ, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_quickstart_defaults_to_prebuilt_and_forwards_source_opt_in() -> None:
    assert run_dashboard_handoff(build_from_source=False) == ""
    assert run_dashboard_handoff(build_from_source=True) == "--build-from-source"


def test_help_documents_explicit_source_build() -> None:
    for script in (QUICKSTART_PATH, DASHBOARD_INSTALL):
        result = subprocess.run(
            ["/bin/bash", str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--build-from-source" in result.stdout


def test_quickstart_requires_rust_only_for_source_build() -> None:
    default = run_quickstart_prerequisites(build_from_source=False)
    source = run_quickstart_prerequisites(build_from_source=True)

    assert default.returncode == 0, default.stdout + default.stderr
    assert "confirm-called" not in default.stdout
    assert source.returncode != 0
    assert "Missing --build-from-source prerequisites" in source.stdout
    assert "rustup" in source.stdout


def test_dashboard_installer_delegates_plugin_acquisition() -> None:
    source = DASHBOARD_INSTALL.read_text()

    assert '"$SCRIPT_DIR/install-plugin.sh"' in source
    assert '"$SCRIPT_DIR/plugin/build.sh"' not in source
