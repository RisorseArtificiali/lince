# Documentation Surface Inventory

> **Status of this document**: committed deliverable of [#212](https://github.com/RisorseArtificiali/lince/issues/212) item 2 — a complete inventory of every documentation surface with a declared owner module, a status classification, and a decided action. The second half of #212 (single-sourcing: schema-generated configuration reference that the skill reference files and docs site both derive from) is follow-up work tracked in the same epic ([#200](https://github.com/RisorseArtificiali/lince/issues/200)) and is **not** part of this file's scope.

Status legend: `generated` (produced by a tool, do not hand-edit) | `hand-curated` (maintained by humans, currently accurate) | `stale` (contains claims that no longer match the code) | `orphaned` (no owner / no consumer) | `deprecated-topic` (documents a deprecated feature; kept intentionally).

| Surface | Owner module | Status | Action |
|---|---|---|---|
| `README.md` | root | hand-curated (macOS backend claim fixed in this PR) | Keep; macOS guidance now points to Seatbelt + migration doc |
| `QUICKSTART.md` | root | hand-curated (nono rows fixed in this PR) | Keep; consider folding into docs site later |
| `quickstart.sh` (embedded help + backend picker) | root | stale (still offers nono, no Seatbelt option) | DEFERRED — code change, follow-up under #212/[#208](https://github.com/RisorseArtificiali/lince/issues/208) |
| `CONTRIBUTING.md` | root | stale (roadmap/issue list still framed around nono validation) | Refresh roadmap section; follow-up under #212 |
| `CLAUDE.md` | root | hand-curated (`lince-config/` added to Project Structure in this PR) | Keep |
| `prompt-quickstart-improvements.md` | root | orphaned (tracked work-note, not user docs) | Convert content to a backlog task, then delete file; follow-up under #212 |
| `docs/README.md` | website (lince.sh) | hand-curated | Keep — local-preview/deploy notes for the GitHub Pages site |
| `docs/index.html`, `docs/changelog/index.html`, `docs/install`, `docs/CNAME` | website (lince.sh) | hand-curated | Keep |
| `docs/documentation/index.html` (Docsify shell) + `_sidebar.md` | website | hand-curated (missing nav entries added in this PR) | Keep |
| `docs/documentation/README.md` | website | hand-curated (nono-integration link retargeted to migration doc in this PR) | Keep |
| `docs/documentation/sandbox/cli-reference.md` | sandbox docs (canonical) | hand-curated | Keep; candidate for schema generation (#212 follow-up) |
| `docs/documentation/sandbox/config-reference.md` | sandbox docs (canonical) | hand-curated | Keep; candidate for schema generation (#212 follow-up) |
| `docs/documentation/sandbox/security-model.md` | sandbox docs (canonical) | hand-curated (`:186` nono claim fixed in this PR) | Keep |
| `docs/documentation/sandbox/migration-nono-to-seatbelt.md` | sandbox docs | hand-curated | Keep — canonical nono-deprecation doc; now linked from sidebar |
| `docs/documentation/dashboard/usage-guide.md` | dashboard docs (canonical) | stale (`:84` wizard backend step says "Pick `bwrap` (agent-sandbox) or `nono`" — the wizard also offers `seatbelt` today, see `plugin/src/sandbox_backend.rs` and `sandbox-levels.md:278`) | DEFERRED — fix alongside the other backend-list updates; follow-up under #212 |
| `docs/documentation/dashboard/config-reference.md` | dashboard docs (canonical) | stale (`:35` backend list lacks seatbelt). The agents-defaults "overwritten on update" claims (`:109`, `:211`) are accurate again: [#199](https://github.com/RisorseArtificiali/lince/issues/199) made always-overwrite (with `.bak` backup + migration warning) the actual `update.sh` behavior, and the doc's migration note documents it | DEFERRED — backend list fix under #212 |
| `docs/documentation/dashboard/agent-examples.md` | dashboard docs | stale (`:28-47` backend choices bwrap/nono only) | DEFERRED — updated under #199 work |
| `docs/documentation/dashboard/sandbox-levels.md` | dashboard docs (canonical) | hand-curated | Keep |
| `docs/documentation/dashboard/sandbox-levels-testing.md` | dashboard docs | stale (nono-era manual test matrix, cells 3.2-3.9) | Rewrite matrix for seatbelt or archive; follow-up under #212 (sidebar entry added in this PR so it is at least reachable) |
| `docs/documentation/messaging/index.md` | messaging docs (canonical) | hand-curated (promoted from `docs/agent-messaging.md` into the docs site) | Keep — full operator guide: opt-in per agent, conversation commands, delivery states, limits and migration |
| `sandbox/README.md` | sandbox | hand-curated (macOS/nono guidance fixed in this PR) | Keep |
| `sandbox/CHEATSHEET.md` | sandbox | hand-curated | Keep |
| `sandbox/config.toml.example` (shipped-file comments) | sandbox | stale (drifts from the embedded `_DEFAULT_CONFIG` in `agent-sandbox`; doc surface read by users at install time) | DEFERRED — alignment + legacy-key migration tracked in [#205](https://github.com/RisorseArtificiali/lince/issues/205) |
| `sandbox/to-be-validated.md` | sandbox | stale (nono 0.24.0-era validation plan) | Archive or rewrite; follow-up under #212 |
| `sandbox/docs/nono-integration.md` | sandbox | deprecated-topic | Keep with deprecation banner pointing to migration doc; follow-up under #212 |
| `sandbox/docs/comparison-agent-sandbox-vs-nono.md` | sandbox | deprecated-topic | Same as above |
| `lince-dashboard/README.md` | dashboard | stale (`:21,:31` still present nono as a current backend and `:32` claims "macOS: nono (required)" — nono is deprecated and Seatbelt is the macOS default) | DEFERRED — same nono→seatbelt sweep as README/QUICKSTART; follow-up under #212 |
| `lince-dashboard/MULTI-AGENT-GUIDE.md` | dashboard | hand-curated (`[profiles.vertex]` example fixed to `[providers.vertex]`; the `:214,:219` "overwritten on update" ownership claims became accurate when #199 landed always-overwrite) | Keep; consider folding guide into docs site |
| `lince-dashboard/config.toml` (shipped-file comments) | dashboard | stale (`:8` says profiles are "auto-discovered from `[profiles.*]`" — renamed to `[providers.*]` in gh#81; `:37-40` says "auto" picks nono on macOS — nono is deprecated since #189) | DEFERRED — comment text fixed with the ownership/merge work in #199; follow-up under #212 |
| `lince-dashboard/tests/MANUAL-5-STATE-VERIFICATION.md` | dashboard | hand-curated (m-15) | Keep |
| `lince-config/README.md` | lince-config | hand-curated | Keep; linked from docs sidebar |
| `lince-dashboard/skills/lince-configure/SKILL.md` + 5 reference files | dashboard skill | hand-curated, condensed duplicates of `docs/documentation` (drift demonstrated: `references/sandbox-config.md:15` lacked seatbelt until this PR) | Single-source via schema generation — #212 follow-up in epic #200 |
| `lince-dashboard/skills/lince-add-supported-agent/SKILL.md` + 3 reference files | dashboard skill | hand-curated (`references/examples.md` overlaps `docs/documentation/dashboard/agent-examples.md`) | De-duplicate examples; keep `hook-templates.md` / `config-schema.md` as skill-unique — #212 follow-up |
| `lince-setup/` (untracked `__pycache__` bytecode only) | none | orphaned | Removed from local checkouts (`rm -rf lince-setup/`); never tracked by git, nothing to commit |
| `backlog/` `*.md` | backlog.md tool | generated | Out of scope — managed by Backlog.md |

## Notes

- **Canonical docs**: `docs/documentation/` is the lince.sh website (Docsify, GitHub Pages) and is the canonical reference surface. Module READMEs link into it; skill reference files are condensed derivatives and the primary drift risk until single-sourcing lands.
- **agents-defaults.toml ownership**: the contradiction between docs ("overwritten on update") and `lince-dashboard/update.sh` actual behavior (preserve + `.dist` sidecar) caused bug #197. #199 resolved it by making always-overwrite (with `.bak` backup + migration warning) the real behavior, so the doc claims match the code again.
- **quickstart.sh**: still auto-selects nono on macOS and offers no Seatbelt option; this is an installer code change, tracked as follow-up under #212/#208 rather than patched in a docs PR.
