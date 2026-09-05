#!/usr/bin/env python3
"""Cross-project addressability of the snapshot store (#23, #24).

Snapshots live under ``snapshots/projects/<sha256(path)[:12]>/``. That hash is
one-way, so before the origin sidecar the store could only ever be addressed
from inside the originating directory: ``snapshot-list`` could not name another
project (#23) and ``snapshot-prune`` could not reclaim one (#24) — including
dirs orphaned by a project that was moved or deleted.

Run with:
    python3 scripts/tests/test_snapshot_store.py
"""

import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def load_agent_sandbox():
    """Import the no-extension ``sandbox/agent-sandbox`` script as a module."""
    path = REPO_ROOT / "sandbox" / "agent-sandbox"
    loader = importlib.machinery.SourceFileLoader("agent_sandbox_snapshot_test", str(path))
    spec = importlib.util.spec_from_loader("agent_sandbox_snapshot_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MOD = load_agent_sandbox()

TIMESTAMPS = (
    "20260101T100000", "20260102T100000", "20260103T100000",
    "20260104T100000", "20260105T100000", "20260106T100000",
)


class SnapshotStoreTestCase(unittest.TestCase):
    """Redirects SNAPSHOT_DIR at a temp store for the duration of a test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = pathlib.Path(self._tmp.name)
        self._real_snapshot_dir = MOD.SNAPSHOT_DIR
        MOD.SNAPSHOT_DIR = self.store
        self.addCleanup(self._restore)

    def _restore(self):
        MOD.SNAPSHOT_DIR = self._real_snapshot_dir
        self._tmp.cleanup()

    def make_project(self, phash, origin=None, count=None):
        """Create a hashed project dir with `count` snapshots in the store."""
        base = self.store / "projects" / phash
        for ts in TIMESTAMPS[: len(TIMESTAMPS) if count is None else count]:
            (base / ts).mkdir(parents=True)
            (base / ts / "f").write_text("x")
        if origin is not None:
            MOD.write_snapshot_origin(base, pathlib.Path(origin))
        return base


class TestOriginSidecar(SnapshotStoreTestCase):
    def test_roundtrip(self):
        base = self.make_project("aaaaaaaaaaaa", origin="/home/u/alpha")
        self.assertEqual(MOD.read_snapshot_origin(base), pathlib.Path("/home/u/alpha"))

    def test_unlabelled_dir_reads_as_none(self):
        """Dirs predating the sidecar must stay readable, not raise."""
        base = self.make_project("bbbbbbbbbbbb")
        self.assertIsNone(MOD.read_snapshot_origin(base))

    def test_sidecar_is_not_mistaken_for_a_snapshot(self):
        """list_snapshots() filters on timestamp-shaped dirs; .origin is a file."""
        base = self.make_project("cccccccccccc", origin="/home/u/alpha", count=2)
        self.assertEqual(len(MOD.list_snapshots(base)), 2)

    def test_write_never_raises_on_unwritable_store(self):
        """A missing label must never fail the snapshot it labels."""
        base = self.store / "projects" / "dddddddddddd"
        base.mkdir(parents=True)
        base.chmod(0o500)
        self.addCleanup(base.chmod, 0o700)
        MOD.write_snapshot_origin(base, pathlib.Path("/home/u/alpha"))  # must not raise
        self.assertIsNone(MOD.read_snapshot_origin(base))


class TestListProjectBases(SnapshotStoreTestCase):
    def test_empty_store(self):
        self.assertEqual(MOD.list_project_snapshot_bases(), [])

    def test_lists_every_project_with_its_origin(self):
        self.make_project("f0b4f623dc47", origin="/home/u/alpha")
        self.make_project("29cf69c51318", origin="/home/u/beta")
        self.make_project("deadbeef1234")  # legacy, unlabelled

        found = MOD.list_project_snapshot_bases()
        self.assertEqual(len(found), 3)
        by_hash = {h: origin for h, _base, origin in found}
        self.assertEqual(by_hash["f0b4f623dc47"], pathlib.Path("/home/u/alpha"))
        self.assertEqual(by_hash["29cf69c51318"], pathlib.Path("/home/u/beta"))
        self.assertIsNone(by_hash["deadbeef1234"])

    def test_label_flags_orphans_and_unlabelled(self):
        """#24: a dir whose project is gone is exactly what needs reclaiming,
        so the listing has to say so rather than print a bare hash."""
        gone = MOD._project_label("0985dd0c546f", pathlib.Path("/home/u/deleted"))
        self.assertIn("missing", gone)

        unlabelled = MOD._project_label("deadbeef1234", None)
        self.assertIn("deadbeef1234", unlabelled)
        self.assertIn("unknown project", unlabelled)

        live = MOD._project_label("f0b4f623dc47", pathlib.Path(self.store))
        self.assertNotIn("missing", live)
        self.assertIn(str(self.store), live)


class TestPruneAcrossProjects(SnapshotStoreTestCase):
    def snap_count(self, phash):
        return len(MOD.list_snapshots(self.store / "projects" / phash))

    def test_prune_reaches_every_project_including_orphans(self):
        """The #24 defect: prune only ever touched the cwd project's hash."""
        self.make_project("f0b4f623dc47", origin="/home/u/alpha")
        self.make_project("29cf69c51318", origin="/home/u/beta")
        self.make_project("0985dd0c546f", origin="/home/u/deleted")
        self.make_project("deadbeef1234")

        total = sum(
            MOD.prune_snapshots(base, 3)
            for _h, base, _o in MOD.list_project_snapshot_bases()
        )

        self.assertEqual(total, 4 * (len(TIMESTAMPS) - 3))
        for phash in ("f0b4f623dc47", "29cf69c51318", "0985dd0c546f", "deadbeef1234"):
            self.assertEqual(self.snap_count(phash), 3, phash)

    def test_prune_is_idempotent(self):
        self.make_project("f0b4f623dc47", origin="/home/u/alpha")
        base = self.store / "projects" / "f0b4f623dc47"
        self.assertEqual(MOD.prune_snapshots(base, 3), len(TIMESTAMPS) - 3)
        self.assertEqual(MOD.prune_snapshots(base, 3), 0)
        self.assertEqual(self.snap_count("f0b4f623dc47"), 3)

    def test_prune_keeps_the_newest(self):
        self.make_project("f0b4f623dc47", origin="/home/u/alpha")
        base = self.store / "projects" / "f0b4f623dc47"
        MOD.prune_snapshots(base, 2)
        kept = [ts for ts, _p, _sz in MOD.list_snapshots(base)]
        self.assertEqual(kept, list(TIMESTAMPS[-2:]))


class TestConfigSnapshotAgents(SnapshotStoreTestCase):
    def test_empty_store(self):
        self.assertEqual(MOD.list_config_snapshot_agents(), [])

    def test_lists_every_agent(self):
        for agent in ("claude", "codex", "gemini"):
            (self.store / "configs" / agent / TIMESTAMPS[0]).mkdir(parents=True)
        self.assertEqual(
            [name for name, _base in MOD.list_config_snapshot_agents()],
            ["claude", "codex", "gemini"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
