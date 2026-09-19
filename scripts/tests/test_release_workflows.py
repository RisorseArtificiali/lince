import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_CI = ROOT / ".github" / "workflows" / "plugin-ci.yml"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
STUB = "lince-dashboard/tests/zellij-host-stub.wat"
EXPLICIT_CARGO = 'PATH="$HOME/.cargo/bin:$PATH" "$HOME/.cargo/bin/cargo"'


def workflow_text(path: Path) -> str:
    assert path.is_file(), f"missing workflow: {path.relative_to(ROOT)}"
    return path.read_text()


def assert_only_explicit_rustup_cargo(text: str) -> None:
    cargo_lines = [line.strip() for line in text.splitlines() if "cargo" in line and not line.lstrip().startswith("#")]
    command_lines = [line for line in cargo_lines if "cargo" in line and ("build" in line or "test" in line)]
    assert command_lines, "workflow must build or test with cargo"
    assert all(EXPLICIT_CARGO in line for line in command_lines), command_lines
    assert not re.search(r"(?:^|[;&|]\s*)cargo\s+(?:build|test)\b", text, re.MULTILINE)


def assert_wasmtime_uses_shared_stub(text: str) -> None:
    assert re.search(r"wasmtime run\s+\\?\s*--preload \"zellij=", text)
    assert STUB in text


def test_plugin_ci_builds_and_runs_wasm_tests_with_shared_stub() -> None:
    text = workflow_text(PLUGIN_CI)

    assert "pull_request:" in text
    assert "dtolnay/rust-toolchain@stable" in text
    assert "targets: wasm32-wasip1" in text
    assert f"{EXPLICIT_CARGO} build --target wasm32-wasip1" in text
    assert f"{EXPLICIT_CARGO} test --target wasm32-wasip1 --no-run" in text
    assert "--message-format=json" in text
    assert ".profile.test == true" in text
    assert_wasmtime_uses_shared_stub(text)
    assert_only_explicit_rustup_cargo(text)


def test_release_builds_validates_and_publishes_checksum_artifacts() -> None:
    text = workflow_text(RELEASE)

    assert "tags:" in text
    assert "v*.*.*" in text
    assert "contents: write" in text
    assert "dtolnay/rust-toolchain@stable" in text
    assert "targets: wasm32-wasip1" in text
    assert f"{EXPLICIT_CARGO} build --release --target wasm32-wasip1" in text
    assert_wasmtime_uses_shared_stub(text)
    assert "sha256sum lince-dashboard.wasm > SHA256SUMS" in text
    assert "gh release create" in text
    assert "lince-dashboard.wasm" in text
    assert "SHA256SUMS" in text
    assert "0.45.1" in text
    assert text.index("wasmtime run") < text.index("gh release create")
    assert_only_explicit_rustup_cargo(text)
