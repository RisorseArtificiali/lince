from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def test_primary_docs_show_both_one_liner_modes() -> None:
    interactive = "curl -sSL https://lince.sh/install | bash"
    defaults = "curl -sSL https://lince.sh/install | bash -s -- --defaults"

    for relative_path in ("README.md", "QUICKSTART.md", "docs/index.html"):
        contents = read(relative_path)
        assert interactive in contents, relative_path
        assert defaults in contents, relative_path


def test_install_guide_covers_zero_friction_contract() -> None:
    guide = read("docs/documentation/install.md")

    for expected in (
        "SHA256SUMS",
        "standalone Python",
        "~/.local/share/lince/python",
        "LINCE_RELEASE_VERSION=vX.Y.Z",
        "--build-from-source",
        "Offline install",
        "WSL",
        "#356",
        "lince update",
        "lince update --check",
    ):
        assert expected in guide


def test_rust_is_source_build_only_in_primary_docs() -> None:
    readme = read("README.md")
    quickstart = read("QUICKSTART.md")
    dashboard = read("lince-dashboard/README.md")

    readme_user_path, readme_source_build = readme.split("## Build from source", 1)
    quickstart_user_path, quickstart_source_build = quickstart.split(
        "## Build from source", 1
    )
    dashboard_user_path, dashboard_source_build = dashboard.split(
        "### Build from source", 1
    )

    for user_path in (readme_user_path, quickstart_user_path, dashboard_user_path):
        assert "rustup" not in user_path.lower()
        assert "wasm32-wasip1" not in user_path

    for source_build in (
        readme_source_build,
        quickstart_source_build,
        dashboard_source_build,
    ):
        assert "rustup" in source_build.lower()
        assert "wasm32-wasip1" in source_build


def test_dashboard_docs_use_native_macos_seatbelt_path() -> None:
    dashboard = read("lince-dashboard/README.md")

    assert "macOS**: [agent-sandbox](../sandbox/) with built-in Seatbelt" in dashboard
    assert "agent-sandbox is Linux-only" not in dashboard


def test_manual_validation_checklist_covers_required_scenarios() -> None:
    checklist = read("docs/documentation/install-validation-checklist.md")

    for expected in (
        "Clean Linux",
        "macOS without Homebrew",
        "Idempotency",
        "Migration from a source-built install",
        "WSL refusal",
    ):
        assert expected in checklist


def test_documentation_navigation_links_install_material() -> None:
    sidebar = read("docs/documentation/_sidebar.md")
    docs_home = read("docs/documentation/README.md")

    for expected in ("install.md", "install-validation-checklist.md"):
        assert expected in sidebar
        assert expected in docs_home
