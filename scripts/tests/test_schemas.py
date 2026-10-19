#!/usr/bin/env python3
"""Schema + version-contract tests for lince-config (#203).

CI-style check (no CI workflows exist yet — runs in the local suite, wired
to CI when m-14 lands): every shipped example/template config must validate
against the published JSON Schemas with zero errors AND zero warnings, and
the generated schemas/*.json files must match the embedded definitions.

Run with:
    python3 scripts/tests/test_schemas.py
"""

import importlib.machinery
import importlib.util
import json
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_lince_config_module():
    path = REPO_ROOT / "lince-config" / "lince-config"
    spec = importlib.util.spec_from_loader(
        "lince_config_under_test",
        importlib.machinery.SourceFileLoader("lince_config_under_test", str(path)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LC = load_lince_config_module()

# Every shipped example/template config in the repo, with its schema target.
SHIPPED_FILES: list[tuple[str, str]] = [
    ("sandbox/config.toml.example", "sandbox-config"),
    ("sandbox/agents-defaults.toml", "sandbox-config"),
    ("lince-dashboard/config.toml", "dashboard-config"),
    ("lince-dashboard/agents-defaults.toml", "dashboard-config"),
    ("docs/examples/lince.toml.example", "lince"),
]


def validate_file(rel_path: str, schema_name: str) -> list:
    with open(REPO_ROOT / rel_path, "rb") as fh:
        parsed = tomllib.load(fh)
    issues: list = []
    if schema_name == "lince":
        issues.extend(LC.check_version_contract(parsed.get("version"), rel_path))
    LC.schema_validate(parsed, LC.SCHEMAS[schema_name if schema_name != "lince" else "lince"], "", issues)
    return issues


class TestShippedExamplesValidate(unittest.TestCase):
    """No shipped config may violate (or even warn against) its own schema."""

    def test_shipped_configs(self):
        for rel_path, schema_name in SHIPPED_FILES:
            issues = validate_file(rel_path, schema_name)
            self.assertEqual(issues, [], f"{rel_path} has schema issues: {issues}")

    def test_registry_files(self):
        for path in sorted((REPO_ROOT / "registry.d").glob("*.toml")):
            with open(path, "rb") as fh:
                parsed = tomllib.load(fh)
            schema = (
                LC.REGISTRY_PROVIDERS_SCHEMA
                if path.name == "providers.toml"
                else LC.REGISTRY_AGENT_SCHEMA
            )
            issues = LC.schema_validate(parsed, schema, "", [])
            self.assertEqual(issues, [], f"registry.d/{path.name} has schema issues: {issues}")

    def test_level_fragments(self):
        """Shipped profile fragments share the sandbox-config schema."""
        for path in sorted((REPO_ROOT / "sandbox" / "profiles").glob("*.toml*")):
            with open(path, "rb") as fh:
                parsed = tomllib.load(fh)
            issues = LC.schema_validate(parsed, LC.SANDBOX_CONFIG_SCHEMA, "", [])
            self.assertEqual(issues, [], f"profiles/{path.name} has schema issues: {issues}")


class TestPublishedSchemasInSync(unittest.TestCase):
    """schemas/*.json are generated from the embedded definitions — no drift."""

    def test_schema_files_match_embedded(self):
        schemas_dir = REPO_ROOT / "schemas"
        for name, schema in LC.SCHEMAS.items():
            path = schemas_dir / f"{name}.schema.json"
            self.assertTrue(path.is_file(), f"missing {path} — run: lince-config schema --write schemas/")
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                on_disk, schema,
                f"{path} is stale — regenerate with: lince-config schema --write schemas/",
            )
        extra = {p.name for p in schemas_dir.glob("*.schema.json")} - {
            f"{n}.schema.json" for n in LC.SCHEMAS
        }
        self.assertFalse(extra, f"unexpected schema files: {extra}")


class TestVersionContract(unittest.TestCase):
    """§2.1 semver contract: explicit older/newer errors, fixing command named."""

    def check(self, version, required=True):
        return LC.check_version_contract(version, "lince.toml", required=required)

    def test_native_version_ok(self):
        self.assertEqual(self.check("2.0"), [])

    def test_missing_version_is_hard_error(self):
        issues = self.check(None)
        self.assertEqual(issues[0]["level"], "error")
        self.assertIn('Add: version = "2.0"', issues[0]["message"])

    def test_missing_version_allowed_for_overlay(self):
        self.assertEqual(self.check(None, required=False), [])

    def test_newer_minor_fails_closed(self):
        issues = self.check("2.5")
        self.assertEqual(issues[0]["level"], "error")
        self.assertIn("newer lince", issues[0]["message"])
        self.assertIn("lince update", issues[0]["message"])

    def test_other_major_is_hard_error(self):
        issues = self.check("1.0")
        self.assertEqual(issues[0]["level"], "error")
        self.assertIn("major version", issues[0]["message"])

    def test_malformed_version(self):
        issues = self.check("2")
        self.assertEqual(issues[0]["level"], "error")
        self.assertIn("MAJOR.MINOR", issues[0]["message"])

    def test_dual_read_window(self):
        """One minor back = read OK with an upgrade hint (simulated native 2.1)."""
        orig = LC.SCHEMA_VERSION_NATIVE
        LC.SCHEMA_VERSION_NATIVE = (2, 1)
        try:
            issues = self.check("2.0")
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["level"], "warn")
            self.assertIn("dual-read window", issues[0]["message"])
            older = self.check("2.0")
            LC.SCHEMA_VERSION_NATIVE = (2, 2)
            beyond = self.check("2.0")
            self.assertEqual(beyond[0]["level"], "error")
            self.assertIn("older than the supported window (2.1)", beyond[0]["message"])
            self.assertIn("lince config migrate", beyond[0]["message"])
            del older
        finally:
            LC.SCHEMA_VERSION_NATIVE = orig


class TestSchemaEngine(unittest.TestCase):
    """The validate engine catches the acceptance-criteria cases."""

    def test_global_mount_mask_list_types(self):
        # JSON Schema checks shape only; runtime rejects local definitions and
        # validates path/source/precedence regardless of what this schema accepts.
        for schema, base, table in (
            (LC.LINCE_SCHEMA, {"version": "2.0"}, "filesystem"),
            (LC.SANDBOX_CONFIG_SCHEMA, {}, "sandbox"),
        ):
            for values in ([], ["/run/media/alessio/Dati"]):
                with self.subTest(table=table, values=values):
                    doc = {**base, table: {"mask_mount_points": values}}
                    self.assertEqual(LC.schema_validate(doc, schema, "", []), [])
            for values in (["/run/media/alessio/Dati", 123], [False], "not an array"):
                with self.subTest(table=table, invalid=values):
                    doc = {**base, table: {"mask_mount_points": values}}
                    issues = LC.schema_validate(doc, schema, "", [])
                    self.assertTrue(any(i["level"] == "error" for i in issues), issues)

    def test_unknown_key_is_warning(self):
        doc = {"version": "2.0", "network": {"default": "deny", "tyop": True}}
        issues = LC.schema_validate(doc, LC.LINCE_SCHEMA, "", [])
        self.assertEqual([i["level"] for i in issues], ["warn"])
        self.assertIn("network.tyop", issues[0]["message"])

    def test_type_error(self):
        doc = {"version": "2.0", "network": {"allowed_hosts": "pypi.org"}}
        issues = LC.schema_validate(doc, LC.LINCE_SCHEMA, "", [])
        self.assertEqual([i["level"] for i in issues], ["error"])
        self.assertIn("should be a array", issues[0]["message"])

    def test_missing_required_key(self):
        issues = LC.schema_validate({"providers": {"x": {}}}, LC.REGISTRY_PROVIDERS_SCHEMA, "", [])
        self.assertTrue(any("required key 'env'" in i["message"] for i in issues))

    def test_enum_violation(self):
        doc = {"version": "2.0", "agents": {"bob": {"event_map": {"x": "busy"}}}}
        issues = LC.schema_validate(doc, LC.LINCE_SCHEMA, "", [])
        self.assertEqual([i["level"] for i in issues], ["error"])
        self.assertIn("must be one of", issues[0]["message"])

    def test_experimental_unknowns_never_error(self):
        doc = {"version": "2.0", "experimental": {"whatever_hatch": "raw"}}
        issues = LC.schema_validate(doc, LC.LINCE_SCHEMA, "", [])
        self.assertEqual(issues, [])

    def test_lifting_rule_wrong_depth_is_caught(self):
        """home_ro_dirs at the lifted level instead of [agents.X.sandbox] (§2.3)."""
        doc = {"version": "2.0", "agents": {"claude": {"home_ro_dirs": [".ssh"]}}}
        issues = LC.schema_validate(doc, LC.LINCE_SCHEMA, "", [])
        self.assertTrue(any("agents.claude.home_ro_dirs" in i["message"] for i in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
