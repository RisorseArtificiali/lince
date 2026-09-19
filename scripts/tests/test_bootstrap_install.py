import os
from pathlib import Path
import pty
import re
import subprocess
import tarfile
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "docs" / "install"
QUICKSTART = (ROOT / "quickstart.sh").read_text()
QUICKSTART_PREREQUISITES = re.search(
    r"^check_prerequisites\(\) \{\n.*?^\}\n",
    QUICKSTART,
    flags=re.MULTILINE | re.DOTALL,
)
assert QUICKSTART_PREREQUISITES is not None


class BootstrapInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.bin_dir = self.root / "bin"
        self.home.mkdir()
        self.bin_dir.mkdir()
        self.log = self.root / "commands.log"
        self.quickstart_log = self.root / "quickstart.log"
        self.zellij_fixture = self.root / "zellij.tar.gz"
        self.python_fixture = self.root / "python.tar.gz"
        self._make_archives()
        self._install_commands()

    def _make_archives(self) -> None:
        zellij = self.root / "zellij"
        zellij.write_text("#!/usr/bin/env bash\necho 'zellij 0.45.1'\n")
        zellij.chmod(0o755)
        with tarfile.open(self.zellij_fixture, "w:gz") as archive:
            archive.add(zellij, arcname="zellij")

        python = self.root / "python" / "bin" / "python3"
        python.parent.mkdir(parents=True)
        python.write_text("#!/usr/bin/env bash\necho '3.11'\n")
        python.chmod(0o755)
        with tarfile.open(self.python_fixture, "w:gz") as archive:
            archive.add(self.root / "python", arcname="python")

    def _write_command(self, name: str, body: str) -> None:
        command = self.bin_dir / name
        command.write_text("#!/usr/bin/env bash\nset -eu\n" + textwrap.dedent(body))
        command.chmod(0o755)

    def _link_command(self, name: str) -> None:
        target = Path("/usr/bin") / name
        if not target.exists():
            target = Path("/bin") / name
        (self.bin_dir / name).symlink_to(target)

    def _install_commands(self) -> None:
        for command in ("awk", "bash", "chmod", "cut", "gzip", "mkdir", "mktemp", "mv", "rm", "tar"):
            self._link_command(command)

        self._write_command(
            "uname",
            """
            case "${1:-}" in
                -s) echo "$TEST_OS" ;;
                -m) echo "$TEST_ARCH" ;;
                *) echo "$TEST_OS" ;;
            esac
            """,
        )
        self._write_command(
            "grep",
            """
            if [ "${TEST_WSL:-0}" = 1 ]; then exit 0; fi
            exec /bin/grep "$@"
            """,
        )
        self._write_command(
            "python3",
            """
            echo "$SYSTEM_PYTHON_VERSION"
            """,
        )
        self._write_command(
            "zellij",
            """
            echo "$SYSTEM_ZELLIJ_VERSION"
            """,
        )
        self._write_command(
            "curl",
            """
            output=
            url=
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    -o|--output) output="$2"; shift 2 ;;
                    http*) url="$1"; shift ;;
                    *) shift ;;
                esac
            done
            printf 'curl %s\n' "$url" >> "$COMMAND_LOG"
            case "$url" in
                *zellij*) /bin/cp "$ZELLIJ_FIXTURE" "$output" ;;
                *cpython*) /bin/cp "$PYTHON_FIXTURE" "$output" ;;
                *) echo "unexpected URL: $url" >&2; exit 2 ;;
            esac
            """,
        )
        self._write_command(
            "sha256sum",
            """
            printf 'sha256sum %s\n' "$*" >> "$COMMAND_LOG"
            [ "${FAIL_CHECKSUM:-0}" != 1 ]
            """,
        )
        self._write_command(
            "git",
            """
            if [ "${1:-}" = init ]; then
                destination=
                for argument in "$@"; do destination="$argument"; done
                /bin/mkdir -p "$destination"
                {
                    printf '%s\n' '#!/usr/bin/env bash'
                    printf '%s\n' '{'
                    printf '%s\n' '  printf "args=%s\\n" "$*"'
                    printf '%s\n' '  printf "path=%s\\n" "$PATH"'
                    printf '%s\n' '  printf "python=%s\\n" "$(command -v python3)"'
                    printf '%s\n' '  printf "zellij=%s\\n" "$(command -v zellij)"'
                    printf '%s\n' '  printf "release=%s\\n" "${LINCE_RELEASE_VERSION:-}"'
                    printf '%s\n' '} > "$QUICKSTART_LOG"'
                } > "$destination/quickstart.sh"
                /bin/chmod +x "$destination/quickstart.sh"
                printf 'git init %s\n' "$destination" >> "$COMMAND_LOG"
            elif [ "${1:-}" = -C ] && [ "${3:-}" = fetch ]; then
                printf 'git fetch %s\n' "$*" >> "$COMMAND_LOG"
            elif [ "${1:-}" = -C ] && [ "${3:-}" = rev-parse ]; then
                printf '%s\n' test-commit
            fi
            """,
        )
        for command in ("bwrap", "sandbox-exec"):
            self._write_command(command, "exit 0\n")

    def run_installer(
        self,
        *,
        os_name: str = "Linux",
        arch: str = "x86_64",
        python_version: str = "3.11",
        zellij_version: str = "zellij 0.45.1",
        wsl: bool = False,
        checksum_failure: bool = False,
        build_from_source: bool = False,
        build_tools: bool = False,
        use_pty: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if build_tools:
            for command in ("cc", "rustup"):
                self._write_command(command, "exit 0\n")
        env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": str(self.bin_dir),
            "TEST_OS": os_name,
            "TEST_ARCH": arch,
            "TEST_WSL": "1" if wsl else "0",
            "SYSTEM_PYTHON_VERSION": python_version,
            "SYSTEM_ZELLIJ_VERSION": zellij_version,
            "FAIL_CHECKSUM": "1" if checksum_failure else "0",
            "COMMAND_LOG": str(self.log),
            "QUICKSTART_LOG": str(self.quickstart_log),
            "ZELLIJ_FIXTURE": str(self.zellij_fixture),
            "PYTHON_FIXTURE": str(self.python_fixture),
            "LINCE_RELEASE_VERSION": "v2.0.0",
        }
        arguments = ["/bin/bash", str(INSTALLER), "--defaults"]
        if build_from_source:
            arguments.append("--build-from-source")
        master_fd, slave_fd = pty.openpty() if use_pty else (None, None)
        try:
            return subprocess.run(
                arguments,
                env=env,
                stdin=slave_fd if use_pty else subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
            )
        finally:
            if master_fd is not None:
                os.close(master_fd)
            if slave_fd is not None:
                os.close(slave_fd)

    def command_log(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def run_quickstart_prerequisites(self, *, build_from_source: bool) -> subprocess.CompletedProcess[str]:
        script = f"""
RED= GREEN= YELLOW= BOLD= DIM= NC=
BUILD_FROM_SOURCE={'true' if build_from_source else 'false'}
check_zellij_version() {{ return 0; }}
has_backend() {{ return 1; }}
confirm() {{ echo confirm-called; return 1; }}
{QUICKSTART_PREREQUISITES.group(0)}
check_prerequisites
"""
        return subprocess.run(
            ["/bin/bash", "-c", script],
            env={**os.environ, "PATH": str(self.bin_dir), "TEST_OS": "Linux"},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_wsl_exits_before_downloading_or_installing(self) -> None:
        result = self.run_installer(wsl=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not supported yet", result.stdout + result.stderr)
        self.assertIn("/issues/356", result.stdout + result.stderr)
        self.assertEqual(self.command_log(), "")

    def test_fast_path_preserves_namespace_and_downloads_nothing(self) -> None:
        python_dir = self.home / ".local/share/lince/python"
        clone_dir = self.home / ".local/share/lince/bootstrap-source"
        python_dir.mkdir(parents=True)
        clone_dir.mkdir(parents=True)
        (python_dir / "keep-me").write_text("persistent")
        (clone_dir / "remove-me").write_text("temporary")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("curl ", self.command_log())
        self.assertTrue((python_dir / "keep-me").is_file())
        self.assertFalse(clone_dir.exists())
        self.assertIn("bootstrap-source", self.command_log())
        self.assertIn("refs/tags/v2.0.0", self.command_log())
        self.assertIn("release=v2.0.0", self.quickstart_log.read_text())

    def test_old_python_and_zellij_are_provisioned_without_optional_tools(self) -> None:
        result = self.run_installer(python_version="3.10", zellij_version="zellij 0.44.0")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / ".local/bin/zellij").is_file())
        standalone = self.home / ".local/share/lince/python/bin/python3"
        self.assertTrue(standalone.is_file())
        handoff = self.quickstart_log.read_text()
        self.assertIn(f"python={standalone}", handoff)
        self.assertIn(f"zellij={self.home / '.local/bin/zellij'}", handoff)
        self.assertIn("node not found; npm-installed agents will be unavailable", result.stdout)
        self.assertIn("jq not found; continuing without it", result.stdout)
        self.assertNotIn("rustup", result.stdout)
        self.assertNotIn("C compiler", result.stdout)

    def test_rerun_reuses_persistent_python_when_system_python_is_old(self) -> None:
        standalone = self.home / ".local/share/lince/python/bin/python3"
        standalone.parent.mkdir(parents=True)
        standalone.write_text("#!/usr/bin/env bash\necho '3.11'\n")
        standalone.chmod(0o755)

        result = self.run_installer(python_version="3.10")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("cpython-", self.command_log())
        self.assertIn(f"python={standalone}", self.quickstart_log.read_text())
        self.assertTrue(standalone.is_file())

    def test_checksum_failure_aborts_before_install_and_clone(self) -> None:
        result = self.run_installer(zellij_version="zellij 0.44.0", checksum_failure=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", (result.stdout + result.stderr).lower())
        self.assertFalse((self.home / ".local/bin/zellij").exists())
        self.assertNotIn("git clone", self.command_log())

    def test_build_from_source_requires_rustup_and_cc_only_when_requested(self) -> None:
        result = self.run_installer(build_from_source=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rustup", result.stdout + result.stderr)
        self.assertIn("C compiler", result.stdout + result.stderr)
        self.assertNotIn("git clone", self.command_log())

    def test_build_from_source_flag_reaches_quickstart_when_tools_exist(self) -> None:
        result = self.run_installer(build_from_source=True, build_tools=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--build-from-source", self.quickstart_log.read_text())

    def test_defaults_handoff_does_not_require_a_terminal(self) -> None:
        result = self.run_installer(use_pty=False)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.quickstart_log.is_file())

    def test_quickstart_documents_build_from_source_option(self) -> None:
        result = subprocess.run(
            ["/bin/bash", str(ROOT / "quickstart.sh"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--build-from-source", result.stdout)

    def test_quickstart_does_not_prompt_for_missing_node_or_jq(self) -> None:
        result = self.run_quickstart_prerequisites(build_from_source=False)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("confirm-called", result.stdout)
        self.assertIn("node not found", result.stdout)
        self.assertIn("jq not found", result.stdout)

    def test_quickstart_requires_source_tools_only_on_opt_in(self) -> None:
        result = self.run_quickstart_prerequisites(build_from_source=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing --build-from-source prerequisites", result.stdout)
        self.assertIn("rustup", result.stdout)
        self.assertIn("C compiler", result.stdout)

    def test_macos_arm64_uses_darwin_assets_without_brew(self) -> None:
        result = self.run_installer(
            os_name="Darwin",
            arch="arm64",
            python_version="3.9",
            zellij_version="unavailable",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        downloads = self.command_log()
        self.assertIn("zellij-aarch64-apple-darwin.tar.gz", downloads)
        self.assertIn("cpython-3.11.16%2B20260901-aarch64-apple-darwin-install_only.tar.gz", downloads)
        self.assertNotIn("brew", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
