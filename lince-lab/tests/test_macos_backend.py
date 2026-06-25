#!/usr/bin/env python3
"""Unit tests for :mod:`lince_lab.macos_backend` (Epic #268 / #263).

Assert the EXACT ``tart``/``ssh``/``scp`` argv built for each
:class:`MacosBackend` method by mocking :mod:`subprocess` — no real VM is
touched. Pins the two load-bearing behaviours: ``exec`` returns the guest code
without raising (the bisect signal); a lifecycle verb raises ``BackendError`` on
a nonzero ``tart`` exit.

Run with:
    python3 lince-lab/tests/test_macos_backend.py
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Put the package dir (lince-lab/) on sys.path so absolute imports resolve.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lince_lab.backend import VmState, VmStatus  # noqa: E402
from lince_lab.errors import BackendError  # noqa: E402
from lince_lab.macos_backend import MacosBackend, _mem_to_mb  # noqa: E402


def _ok(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


_TEMPLATE = json.dumps(
    {
        "images": [{"location": "ghcr.io/cirruslabs/macos-sequoia-base:latest", "arch": "arm64"}],
        "cpus": 4,
        "memory": "2GiB",
        "disk": "40GiB",
    }
)


class CreateArgvTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MacosBackend()

    def _patch_run(self, result: subprocess.CompletedProcess) -> mock.MagicMock:
        patcher = mock.patch("lince_lab.macos_backend.subprocess.run", return_value=result)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_mem_to_mb(self) -> None:
        self.assertEqual(_mem_to_mb("2GiB"), 2048)
        self.assertEqual(_mem_to_mb("512MiB"), 512)
        self.assertEqual(_mem_to_mb("4GB"), 4000)

    def test_create_clones_image_then_sets_resources(self) -> None:
        run = self._patch_run(_ok())
        self.backend.create("lince-lab-x", _TEMPLATE)
        argvs = [c.args[0] for c in run.call_args_list]
        self.assertEqual(
            argvs[0],
            ["tart", "clone", "ghcr.io/cirruslabs/macos-sequoia-base:latest", "lince-lab-x"],
        )
        # resources applied via `tart set` (cpu + memory in MB); disk omitted (grow-only).
        self.assertEqual(argvs[1], ["tart", "set", "lince-lab-x", "--cpu", "4", "--memory", "2048"])

    def test_create_missing_image_raises(self) -> None:
        self._patch_run(_ok())
        with self.assertRaises(BackendError):
            self.backend.create("lince-lab-x", json.dumps({"images": []}))


class LifecycleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MacosBackend()

    def test_stop_runs_tart_stop(self) -> None:
        with mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok()) as run:
            self.backend.stop("lince-lab-x")
        self.assertEqual(run.call_args.args[0], ["tart", "stop", "lince-lab-x"])

    def test_delete_stops_then_deletes(self) -> None:
        with mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok()) as run:
            self.backend.delete("lince-lab-x")
        argvs = [c.args[0] for c in run.call_args_list]
        self.assertIn(["tart", "delete", "lince-lab-x"], argvs)

    def test_status_running_and_absent(self) -> None:
        records = [{"Name": "lince-lab-x", "State": "running"}]
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            return_value=_ok(stdout=json.dumps(records)),
        ) as run:
            state = self.backend.status("lince-lab-x")
        self.assertEqual(run.call_args.args[0], ["tart", "list", "--format", "json"])
        self.assertEqual(state.status, VmStatus.RUNNING)
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            return_value=_ok(stdout=json.dumps(records)),
        ):
            self.assertEqual(self.backend.status("ghost").status, VmStatus.ABSENT)

    def test_list_maps_states_and_skips_oci_and_snapshots(self) -> None:
        records = [
            {"Name": "lince-lab-a", "State": "running"},
            {"Name": "lince-lab-b", "State": "stopped"},
            {"Name": "ghcr.io/cirruslabs/macos-sequoia-base:latest", "State": "stopped", "Source": "OCI"},
            {"Name": "lince-lab-a__snap__base", "State": "stopped"},
        ]
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            return_value=_ok(stdout=json.dumps(records)),
        ):
            states = self.backend.list()
        self.assertEqual(
            [(s.name, s.status) for s in states],
            [("lince-lab-a", VmStatus.RUNNING), ("lince-lab-b", VmStatus.STOPPED)],
        )

    def test_start_spawns_detached_run_and_waits_for_ip(self) -> None:
        fake_proc = mock.MagicMock(spec=subprocess.Popen)
        with (
            mock.patch("lince_lab.macos_backend.subprocess.Popen", return_value=fake_proc) as popen,
            mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok(stdout="192.168.64.7\n")),
        ):
            self.backend.start("lince-lab-x")
        self.assertEqual(popen.call_args.args[0], ["tart", "run", "lince-lab-x", "--no-graphics"])
        self.assertIs(self.backend._running["lince-lab-x"], fake_proc)


class ExecTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MacosBackend()

    def test_exec_builds_ssh_remote_command_and_returns_code(self) -> None:
        # First subprocess.run = `tart ip`; second = the ssh exec.
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok(stdout="hi", returncode=0)],
        ) as run:
            result = self.backend.exec("lince-lab-x", ["sh", "-c", "echo hi"])
        ssh_argv = run.call_args_list[1].args[0]
        self.assertEqual(ssh_argv[0], "ssh")
        self.assertEqual(ssh_argv[-2], "admin@10.0.0.5")
        # The remote command is one shell-quoted string (no host-side word-split).
        self.assertEqual(ssh_argv[-1], "sh -c 'echo hi'")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "hi")

    def test_exec_injects_workdir_and_env(self) -> None:
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok()],
        ) as run:
            self.backend.exec("lince-lab-x", ["make", "test"], workdir="/work", env={"CI": "1"})
        remote = run.call_args_list[1].args[0][-1]
        self.assertEqual(remote, "cd /work && env CI=1 make test")

    def test_exec_returns_guest_nonzero_without_raising(self) -> None:
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok(stderr="boom", returncode=1)],
        ):
            result = self.backend.exec("lince-lab-x", ["false"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, "boom")


class CopyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MacosBackend()

    def test_copy_in_scp_target(self) -> None:
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok()],
        ) as run:
            self.backend.copy_in("lince-lab-x", "./work", "/work", recursive=True)
        scp = run.call_args_list[1].args[0]
        self.assertEqual(scp[0], "scp")
        self.assertIn("-r", scp)
        self.assertEqual(scp[-2:], ["./work", "admin@10.0.0.5:/work"])

    def test_copy_out_scp_source(self) -> None:
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok()],
        ) as run:
            self.backend.copy_out("lince-lab-x", "/etc/hosts", "./hosts")
        scp = run.call_args_list[1].args[0]
        self.assertEqual(scp[-2:], ["admin@10.0.0.5:/etc/hosts", "./hosts"])

    def test_copy_in_raises_on_scp_failure(self) -> None:
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            side_effect=[_ok(stdout="10.0.0.5\n"), _ok(stderr="nope", returncode=1)],
        ):
            with self.assertRaises(BackendError):
                self.backend.copy_in("lince-lab-x", "./a", "/a")


class SnapshotTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MacosBackend()

    def test_snapshot_list_filters_by_naming(self) -> None:
        records = [
            {"Name": "lince-lab-x", "State": "running"},
            {"Name": "lince-lab-x__snap__base", "State": "stopped"},
            {"Name": "lince-lab-x__snap__cand-2", "State": "stopped"},
            {"Name": "lince-lab-y", "State": "stopped"},
        ]
        with mock.patch(
            "lince_lab.macos_backend.subprocess.run",
            return_value=_ok(stdout=json.dumps(records)),
        ):
            tags = self.backend.snapshot_list("lince-lab-x")
        self.assertEqual(sorted(tags), ["base", "cand-2"])

    def test_snapshot_delete(self) -> None:
        with mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok()) as run:
            self.backend.snapshot_delete("lince-lab-x", "base")
        self.assertEqual(run.call_args.args[0], ["tart", "delete", "lince-lab-x__snap__base"])

    def test_snapshot_create_clones_stopped_golden(self) -> None:
        # VM is stopped already (status returns STOPPED) → no stop/start dance.
        with (
            mock.patch.object(self.backend, "status", return_value=VmState("lince-lab-x", VmStatus.STOPPED, [])),
            mock.patch.object(self.backend, "snapshot_list", return_value=[]),
            mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok()) as run,
        ):
            self.backend.snapshot_create("lince-lab-x", "base")
        argvs = [c.args[0] for c in run.call_args_list]
        self.assertIn(["tart", "clone", "lince-lab-x", "lince-lab-x__snap__base"], argvs)

    def test_snapshot_apply_restores_from_golden(self) -> None:
        with (
            mock.patch.object(self.backend, "snapshot_list", return_value=["base"]),
            mock.patch.object(self.backend, "stop"),
            mock.patch.object(self.backend, "start") as start,
            mock.patch("lince_lab.macos_backend.subprocess.run", return_value=_ok()) as run,
        ):
            self.backend.snapshot_apply("lince-lab-x", "base")
        argvs = [c.args[0] for c in run.call_args_list]
        self.assertIn(["tart", "delete", "lince-lab-x"], argvs)
        self.assertIn(["tart", "clone", "lince-lab-x__snap__base", "lince-lab-x"], argvs)
        start.assert_called_once_with("lince-lab-x")

    def test_snapshot_apply_unknown_tag_raises(self) -> None:
        with mock.patch.object(self.backend, "snapshot_list", return_value=[]):
            with self.assertRaises(BackendError):
                self.backend.snapshot_apply("lince-lab-x", "missing")


class OpenCaptureTestCase(unittest.TestCase):
    def test_open_capture_copies_ht_and_spawns_over_ssh(self) -> None:
        from lince_lab.lima_backend import LimaCaptureChannel

        with tempfile.NamedTemporaryFile(suffix="-ht-darwin") as host_ht:
            host_ht.write(b"#!/bin/sh\n")
            host_ht.flush()
            fake_proc = mock.MagicMock(spec=subprocess.Popen)
            fake_proc.stdout = None
            fake_proc.stderr = None
            with (
                mock.patch.dict("os.environ", {"LINCE_LAB_HT": host_ht.name}, clear=False),
                mock.patch(
                    "lince_lab.macos_backend.subprocess.run",
                    side_effect=[
                        _ok(stdout="10.0.0.5\n"),  # _ip for copy_in
                        _ok(),  # scp copy_in
                        _ok(stdout="10.0.0.5\n"),  # _ip for chmod
                        _ok(),  # ssh chmod +x
                        _ok(stdout="10.0.0.5\n"),  # _ip for the spawn
                    ],
                ),
                mock.patch("lince_lab.macos_backend.subprocess.Popen", return_value=fake_proc) as popen,
            ):
                backend = MacosBackend()
                channel = backend.open_capture("lince-lab-x", ["./tui"], cols=80, rows=24)
        spawn = popen.call_args.args[0]
        self.assertEqual(spawn[0], "ssh")
        self.assertEqual(
            spawn[-1],
            "/tmp/lince-lab-ht --size 80x24 --subscribe init,output,snapshot -- ./tui",
        )
        self.assertIsInstance(channel, LimaCaptureChannel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
