import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-plugin.sh"


class PluginInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.release = self.root / "release"
        self.bin_dir = self.root / "bin"
        self.tmp_dir = self.root / "tmp"
        self.module = self.root / "lince-dashboard"
        self.home.mkdir()
        self.release.mkdir()
        self.bin_dir.mkdir()
        self.tmp_dir.mkdir()
        (self.module / "plugin").mkdir(parents=True)
        if INSTALLER.exists():
            shutil.copy2(INSTALLER, self.module / "install-plugin.sh")
        shutil.copy2(ROOT / "plugin/build.sh", self.module / "plugin/build.sh")
        self.command_log = self.root / "commands.log"

    def write_release(self, payload: bytes = b"release wasm", checksum: str | None = None) -> None:
        artifact = self.release / "lince-dashboard.wasm"
        artifact.write_bytes(payload)
        digest = checksum or hashlib.sha256(payload).hexdigest()
        (self.release / "SHA256SUMS").write_text(f"{digest}  lince-dashboard.wasm\n")

    def write_command(self, name: str, body: str) -> Path:
        command = self.bin_dir / name
        command.write_text("#!/usr/bin/env bash\nset -eu\n" + textwrap.dedent(body))
        command.chmod(0o755)
        return command

    def run_installer(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        installer = self.module / "install-plugin.sh"
        self.assertTrue(installer.exists(), f"missing installer: {installer}")
        return subprocess.run(
            ["/bin/bash", str(installer), *arguments],
            env={
                **os.environ,
                "HOME": str(self.home),
                "LINCE_RELEASE_BASE_URL": self.release.as_uri(),
                "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
                "COMMAND_LOG": str(self.command_log),
                "TMPDIR": str(self.tmp_dir),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    @property
    def installed(self) -> Path:
        return self.home / ".config/zellij/plugins/lince-dashboard.wasm"

    def test_default_installs_verified_release_without_rust(self) -> None:
        self.write_release()
        for command in ("cargo", "rustc", "rustup"):
            self.write_command(command, f"echo {command} >> \"$COMMAND_LOG\"; exit 99\n")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed.read_bytes(), b"release wasm")
        self.assertFalse(self.command_log.exists(), self.command_log.read_text() if self.command_log.exists() else "")
        self.assertEqual(list(self.tmp_dir.iterdir()), [])

    def test_checksum_mismatch_keeps_existing_plugin(self) -> None:
        self.installed.parent.mkdir(parents=True)
        self.installed.write_bytes(b"known good")
        self.write_release(checksum="0" * 64)

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", (result.stdout + result.stderr).lower())
        self.assertIn("--build-from-source", result.stdout + result.stderr)
        self.assertEqual(self.installed.read_bytes(), b"known good")
        self.assertEqual(list(self.installed.parent.glob(".lince-dashboard.wasm.new.*")), [])

    def test_download_failure_does_not_fall_back_or_create_partial_plugin(self) -> None:
        for command in ("cargo", "rustc", "rustup"):
            self.write_command(command, f"echo {command} >> \"$COMMAND_LOG\"; exit 99\n")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--build-from-source", result.stdout + result.stderr)
        self.assertFalse(self.installed.exists())
        self.assertFalse(self.command_log.exists(), self.command_log.read_text() if self.command_log.exists() else "")

    def test_checksum_manifest_must_name_the_release_artifact(self) -> None:
        self.write_release()
        (self.release / "SHA256SUMS").write_text(
            f"{hashlib.sha256(b'release wasm').hexdigest()}  another-file.wasm\n"
        )

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no valid checksum", (result.stdout + result.stderr).lower())
        self.assertFalse(self.installed.exists())

    def test_reinstall_replaces_plugin_and_keeps_backup(self) -> None:
        self.installed.parent.mkdir(parents=True)
        self.installed.write_bytes(b"old wasm")
        self.write_release(payload=b"new wasm")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed.read_bytes(), b"new wasm")
        backups = list(self.installed.parent.glob("lince-dashboard.wasm.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old wasm")

    def test_source_flag_uses_existing_build_path_and_skips_download(self) -> None:
        cargo = self.write_command(
            "cargo",
            """
            echo cargo >> "$COMMAND_LOG"
            mkdir -p target/wasm32-wasip1/release
            printf 'source wasm' > target/wasm32-wasip1/release/lince-dashboard.wasm
            """,
        )
        rustc = self.write_command("rustc", "echo rustc 1.90.0\n")
        self.write_command(
            "rustup",
            f"""
            case "${{1:-}} ${{2:-}}" in
                "which cargo") printf '%s\\n' '{cargo}' ;;
                "which rustc") printf '%s\\n' '{rustc}' ;;
                "target list") echo 'wasm32-wasip1 (installed)' ;;
                *) exit 0 ;;
            esac
            """,
        )

        result = self.run_installer("--build-from-source")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed.read_bytes(), b"source wasm")
        self.assertEqual(self.command_log.read_text().splitlines(), ["cargo"])


if __name__ == "__main__":
    unittest.main()
