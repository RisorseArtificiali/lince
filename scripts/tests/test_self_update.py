import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "lince-updater" / "lince-update"
INSTALLER = ROOT / "lince-updater" / "install.sh"
QUICKSTART = ROOT / "quickstart.sh"
LINCE_SHIM = ROOT / "lince-dashboard" / "lince"


class UpdateFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.bin = root / "bin"
        self.source = root / "release-source"
        self.log = root / "updates.log"
        self.home.mkdir()
        self.bin.mkdir()
        self.source.mkdir()
        self._write_fake_git()

    def _write_fake_git(self) -> None:
        command = self.bin / "git"
        command.write_text(
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            'if [ "${1:-}" = init ]; then\n'
            '  for destination; do :; done\n'
            '  mkdir -p "$destination"\n'
            '  cp -R "$TEST_RELEASE_SOURCE/." "$destination/"\n'
            'elif [ "${1:-}" = -C ] && [ "${3:-}" = rev-parse ]; then\n'
            '  printf "%s\\n" test-commit\n'
            "fi\n"
        )
        command.chmod(0o755)

    def install_marker(self, name: str) -> None:
        markers = {
            "sandbox": self.home / ".local/bin/agent-sandbox",
            "lince-config": self.home / ".local/bin/lince-config",
            "lince-dashboard": self.home / ".config/zellij/plugins/lince-dashboard.wasm",
            "lince-lab": self.home / ".local/bin/lince-lab",
            "lince-messages": self.home / ".local/bin/lince-msg",
        }
        marker = markers[name]
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(name)
        marker.chmod(0o755)

    def add_release_module(self, name: str, *, fail: bool = False) -> None:
        module = self.source / name
        module.mkdir()
        update = module / "update.sh"
        update.write_text(
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            f'printf "%s\\n" {name!r} >> "$TEST_UPDATE_LOG"\n'
            + ("exit 7\n" if fail else "")
        )
        update.chmod(0o755)

    def run(self, *args: str, version: str = "v2.0.0") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", str(UPDATER), *args],
            env={
                **os.environ,
                "HOME": str(self.home),
                "PATH": f"{self.bin}:{os.environ['PATH']}",
                "LINCE_LATEST_VERSION": version,
                "LINCE_REPOSITORY_URL": "https://example.invalid/lince.git",
                "TEST_RELEASE_SOURCE": str(self.source),
                "TEST_UPDATE_LOG": str(self.log),
            },
            capture_output=True,
            text=True,
            check=False,
        )


def test_check_reports_versions_without_writing() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = UpdateFixture(Path(directory))
        version_file = fixture.home / ".local/share/lince/release-version"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("v1.4.0\n")
        before = sorted(
            (path.relative_to(fixture.home), path.read_bytes())
            for path in fixture.home.rglob("*")
            if path.is_file()
        )

        result = fixture.run("--check")

        after = sorted(
            (path.relative_to(fixture.home), path.read_bytes())
            for path in fixture.home.rglob("*")
            if path.is_file()
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Installed: v1.4.0" in result.stdout
        assert "Latest:    v2.0.0" in result.stdout
        assert "Update available" in result.stdout
        assert before == after
        assert not fixture.log.exists()


def test_check_rejects_a_non_release_tag() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = UpdateFixture(Path(directory))

        result = fixture.run("--check", version="v2.0.0/extra")

        assert result.returncode != 0
        assert "invalid latest release version" in result.stderr


def test_update_runs_only_installed_modules_and_records_version_last() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = UpdateFixture(Path(directory))
        for module in ("sandbox", "lince-config", "lince-dashboard", "lince-lab", "lince-messages"):
            fixture.add_release_module(module)
        for installed in ("sandbox", "lince-dashboard", "lince-messages"):
            fixture.install_marker(installed)
        version_file = fixture.home / ".local/share/lince/release-version"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("v1.4.0\n")
        config = fixture.home / ".config/lince-dashboard/config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('theme = "mine"\n')

        result = fixture.run()

        assert result.returncode == 0, result.stdout + result.stderr
        assert fixture.log.read_text().splitlines() == ["lince-dashboard", "sandbox", "lince-messages"]
        assert version_file.read_text() == "v2.0.0\n"
        assert config.read_text() == 'theme = "mine"\n'


def test_failed_module_update_keeps_previous_version_marker() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = UpdateFixture(Path(directory))
        fixture.add_release_module("sandbox", fail=True)
        fixture.install_marker("sandbox")
        version_file = fixture.home / ".local/share/lince/release-version"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("v1.4.0\n")

        result = fixture.run()

        assert result.returncode != 0
        assert version_file.read_text() == "v1.4.0\n"


def test_update_checks_out_tag_when_same_named_branch_exists() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repository = root / "repository"
        home = root / "home"
        log = root / "updates.log"
        repository.mkdir()
        home.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
        module = repository / "sandbox"
        module.mkdir()
        update = module / "update.sh"
        update.write_text('#!/usr/bin/env bash\nprintf "tag\\n" >> "$TEST_UPDATE_LOG"\n')
        update.chmod(0o755)
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "tag source"], cwd=repository, check=True)
        subprocess.run(["git", "tag", "v2.0.0"], cwd=repository, check=True)
        subprocess.run(["git", "switch", "-q", "-c", "v2.0.0"], cwd=repository, check=True)
        update.write_text('#!/usr/bin/env bash\nprintf "branch\\n" >> "$TEST_UPDATE_LOG"\n')
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "same-named branch"], cwd=repository, check=True)
        marker = home / ".local/bin/agent-sandbox"
        marker.parent.mkdir(parents=True)
        marker.write_text("installed")
        marker.chmod(0o755)

        result = subprocess.run(
            ["/bin/bash", str(UPDATER)],
            env={
                **os.environ,
                "HOME": str(home),
                "LINCE_LATEST_VERSION": "v2.0.0",
                "LINCE_REPOSITORY_URL": str(repository),
                "TEST_UPDATE_LOG": str(log),
            },
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert log.read_text() == "tag\n"


def test_update_prefers_bootstrap_managed_python() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = UpdateFixture(Path(directory))
        fixture.add_release_module("sandbox")
        fixture.install_marker("sandbox")
        managed_python = fixture.home / ".local/share/lince/python/bin/python3"
        managed_python.parent.mkdir(parents=True)
        managed_python.write_text("#!/usr/bin/env bash\nexit 0\n")
        managed_python.chmod(0o755)
        update = fixture.source / "sandbox/update.sh"
        update.write_text(
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            'command -v python3 > "$TEST_UPDATE_LOG"\n'
        )
        update.chmod(0o755)

        result = fixture.run()

        assert result.returncode == 0, result.stdout + result.stderr
        assert fixture.log.read_text().strip() == str(managed_python)


def test_lince_dispatches_update_and_keeps_dashboard_default() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        shutil.copy2(LINCE_SHIM, bin_dir / "lince")
        log = root / "calls"
        for command in ("lince-update", "lince-dashboard-launch"):
            path = bin_dir / command
            path.write_text(
                "#!/usr/bin/env bash\n"
                f'printf "%s:%s\\n" {command!r} "$*" >> {str(log)!r}\n'
            )
            path.chmod(0o755)

        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        update = subprocess.run([str(bin_dir / "lince"), "update", "--check"], env=env, check=False)
        launch = subprocess.run([str(bin_dir / "lince"), "--print-layout"], env=env, check=False)

        assert update.returncode == 0
        assert launch.returncode == 0
        assert log.read_text().splitlines() == [
            "lince-update:--check",
            "lince-dashboard-launch:--print-layout",
        ]


def test_updater_module_contract_and_quickstart_install() -> None:
    for script in (INSTALLER, ROOT / "lince-updater/update.sh", ROOT / "lince-updater/uninstall.sh"):
        assert script.is_file()
    quickstart = QUICKSTART.read_text()
    assert 'bash "$SCRIPT_DIR/lince-updater/install.sh"' in quickstart
