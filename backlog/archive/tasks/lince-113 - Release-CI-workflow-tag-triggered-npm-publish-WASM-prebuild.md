---
id: LINCE-113
title: Release CI workflow (tag-triggered npm publish + WASM prebuild)
status: To Do
assignee: []
created_date: '2026-05-11 15:00'
updated_date: '2026-09-19 13:35'
labels:
  - enhancement
  - ci
  - epic-97
milestone: m-14
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/lince/issues/104'
  - 'https://github.com/RisorseArtificiali/lince/issues/97'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## TLDR

Add a GitHub Actions workflow triggered on `v*` tag pushes that builds the WASM dashboard plugin via the rustup-managed toolchain, stages all module sources + the prebuilt WASM into `dist/`, syncs the package version to the tag, and publishes `@risorseartificiali/lince-cli` to npm.

## Why

Without CI, every release requires a contributor with the right Rust toolchain, npm credentials, and a clean machine. With CI, a maintainer just pushes a tag and a fresh release lands on npm. Prebuilding the WASM in CI is what removes the `cargo`/`rustup` dependency from end-user machines.

## Implementation plan

1. `.github/workflows/release.yml`: `on: push: tags: ["v*"]`, single job `publish` on `ubuntu-latest`, `contents: read` permission.
2. Toolchain: `dtolnay/rust-toolchain@stable` with `targets: wasm32-wasip1` (system cargo lacks the target per CLAUDE.md).
3. WASM build: `cd lince-dashboard/plugin && cargo build --release --target wasm32-wasip1`.
4. Stage `dist/`: mkdir dist/lince-dashboard, cp WASM artifact, then explicit-allowlist cp of each module (`sandbox`, `lince-config`, `lince-cli`, `voxcode`, `lince-dashboard` non-source files, `installer.sh`). Do NOT `cp -r .`.
5. Version sync: `npm version "${GITHUB_REF#refs/tags/v}" --no-git-tag-version`.
6. Node setup: `actions/setup-node@v4` with `registry-url: https://registry.npmjs.org`, `scope: @risorseartificiali`.
7. `npm publish --access public` with `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}`.
8. Pre-publish sanity: `npm pack --dry-run` printed in the log.
9. Document `NPM_TOKEN` in workflow header + contributing docs (Granular Access Token scoped to the package, publish permission).

## Dependencies

- Blocks: #105
- Blocked by: #103

## References

- Epic: #97
- Plan: `/home/maeste/.claude/plans/lince-unified-cli-npm.md` (section "Release workflow")
- CLAUDE.md: Rust/WASM toolchain note
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Workflow file lints clean with actionlint (or equivalent).
- [ ] #2 Pushing a test tag (e.g. v0.0.1-test1) to a personal fork with NPM_TOKEN configured triggers a successful run ending in npm publish (or fails specifically on the publish step if no token — build + stage must succeed).
- [ ] #3 The published tarball contains dist/lince-dashboard/lince_dashboard.wasm (prebuilt).
- [ ] #4 The published tarball does NOT contain .git/, .github/, tests/, or any module source outside dist/.
- [ ] #5 `npm install -g @risorseartificiali/lince-cli@<tag>` on a fresh Linux machine succeeds and lince-installer is on PATH.
- [ ] #6 Workflow fails fast and clearly if NPM_TOKEN is missing or invalid.
<!-- AC:END -->
