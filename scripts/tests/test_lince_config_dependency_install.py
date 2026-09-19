from pathlib import Path
import os
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def test_install_and_update_bind_pip_to_selected_python() -> None:
    for relative in ("lince-config/install.sh", "lince-config/update.sh"):
        source = (ROOT / relative).read_text()
        assert '"$LINCE_CONFIG_PYTHON" -m pip' in source


def test_managed_python_install_is_bound_to_lince_python_shim() -> None:
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        managed = home / ".local/share/lince/python/bin/python3"
        managed.parent.mkdir(parents=True)
        managed.write_text("#!/bin/sh\nexit 0\n")
        managed.chmod(0o755)

        for _ in range(2):
            result = subprocess.run(
                ["bash", str(ROOT / "lince-config/install-command.sh")],
                env={
                    **os.environ,
                    "HOME": str(home),
                    "LINCE_CONFIG_PYTHON": str(managed),
                    "LINCE_CONFIG_USE_MANAGED": "true",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr

        command = home / ".local/bin/lince-config"
        shim = home / ".local/bin/lince-python"
        assert command.read_text().splitlines()[0] == "#!/usr/bin/env lince-python"
        assert shim.is_file()
        assert "Managed by LINCE for the standalone bootstrap interpreter" in shim.read_text()


def test_system_python_install_keeps_native_shebang() -> None:
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)

        result = subprocess.run(
            ["bash", str(ROOT / "lince-config/install-command.sh")],
            env={
                **os.environ,
                "HOME": str(home),
                "LINCE_CONFIG_PYTHON": "/usr/bin/python3",
                "LINCE_CONFIG_USE_MANAGED": "false",
            },
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        command = home / ".local/bin/lince-config"
        assert command.read_text().splitlines()[0] == "#!/usr/bin/env python3"
        assert not (home / ".local/bin/lince-python").exists()


def test_install_and_direct_update_use_one_runtime_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        home = root / "home"
        system_bin = root / "system-bin"
        python_path = root / "pythonpath"
        log = root / "python.log"
        home.mkdir()
        system_bin.mkdir()
        python_path.mkdir()
        (python_path / "tomlkit.py").write_text('__version__ = "test"\n')

        real_python = Path(sys.executable)

        def write_runtime(path: Path, label: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "#!/bin/sh\n"
                f'printf "%s\\n" {label!r} >> "$PYTHON_RUNTIME_LOG"\n'
                f'exec {str(real_python)!r} "$@"\n'
            )
            path.chmod(0o755)

        system_python = system_bin / "python3"
        managed_python = home / ".local/share/lince/python/bin/python3"
        write_runtime(system_python, "system")
        write_runtime(managed_python, "managed")
        env = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{system_bin}:{os.environ['PATH']}",
            "PYTHONPATH": str(python_path),
            "PYTHON_RUNTIME_LOG": str(log),
            "LINCE_PYTHON_CMD": str(system_python),
        }

        installed = subprocess.run(
            ["bash", str(ROOT / "lince-config/install.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert installed.returncode == 0, installed.stdout + installed.stderr
        command = home / ".local/bin/lince-config"
        assert command.read_text().splitlines()[0] == "#!/usr/bin/env python3"

        env.pop("LINCE_PYTHON_CMD")
        updated = subprocess.run(
            ["bash", str(ROOT / "lince-config/update.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert updated.returncode == 0, updated.stdout + updated.stderr
        assert command.read_text().splitlines()[0] == "#!/usr/bin/env lince-python"

        executed = subprocess.run(
            [str(command), "--help"],
            env={**env, "PATH": f"{home / '.local/bin'}:{env['PATH']}"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert log.read_text().splitlines()[-1] == "managed"
