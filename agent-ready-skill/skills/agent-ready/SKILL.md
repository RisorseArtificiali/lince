---
name: agent-ready
description: "Assess and improve a project's readiness for agentic coding. Analyzes 8 dimensions (instructions, navigability, testing, CI/CD, specs, skills, docs, Claude-specific) producing a quantitative 0-100 score and actionable guidance. Use when evaluating how well a codebase supports AI-assisted development, or when the user mentions 'agent ready', 'agentic readiness', or 'AI-ready project'."
argument-hint: "[scan|fix|report|diff] [path-or-github-url]"
allowed-tools: Bash(git:*) Bash(find:*) Bash(wc:*) Bash(mv:*) Bash(mkdir:*) Read Grep Glob Write
---

# Agentic Readiness Assessment

You are an expert at evaluating how well a codebase is prepared for agentic coding (AI-assisted autonomous development). Analyze projects across 8 weighted dimensions and produce a quantitative score (0-100) plus qualitative guidance.

## Routing

Parse `$ARGUMENTS` to determine the sub-command and target:

1. **Extract sub-command** (first word): `scan` (default), `fix`, `report`, or `diff`
2. **Extract target** (remaining arguments): a GitHub URL, local path, or empty (use cwd)
3. If first word is not a recognized sub-command, treat entire argument as target and default to `scan`

| Input | Sub-command | Target |
|-------|------------|--------|
| _(empty)_ | scan | cwd |
| `scan` | scan | cwd |
| `scan /path/to/project` | scan | /path/to/project |
| `fix` | fix | cwd |
| `report` | report | cwd |
| `diff` | diff | cwd |
| `https://github.com/org/repo` | scan | clone URL to /tmp/ |
| `scan https://github.com/org/repo` | scan | clone URL to /tmp/ |

**Target resolution**:
- If target starts with `http` or `git@`: clone with `git clone --depth 1 <url> /tmp/agent-ready-$(date +%s)` and set as target
- If target is a local path: use it directly
- If empty: use current working directory

## Sub-command Dispatch

Route to the appropriate skill:
- **scan**: invoke `/agent-ready-scan <target>`
- **fix**: invoke `/agent-ready-fix <target>`
- **report**: invoke `/agent-ready-report <target>`
- **diff**: invoke `/agent-ready-diff <target>`

## Scoring Reference

For full scoring details, sub-criteria definitions, and the JSON schema, see [references/scoring.md](references/scoring.md).

### Quick Reference

**8 Dimensions** (weight totals 100):
1. Agent Instructions (20) — CLAUDE.md, hierarchical rules, build/test/lint docs
2. Project Navigability (18) — Structure, index files, README, naming consistency
3. Testing & Validation (16) — Test suite, documented commands, coverage, speed
4. CI/CD & Automation (10) — Pipeline, linting, pre-commit hooks
5. Spec-Driven Workflow (12) — Specs, issue templates, ADR, acceptance criteria
6. Skills & Tooling (8) — Skills, Makefile, scripts, MCP config
7. Documentation (8) — Linked docs, API docs, architecture, changelog
8. Claude-Specific (8) — .claude/ dir, settings, hooks, MCP integration

**Levels**: 🔴 0-30 Not Ready | 🟡 31-60 Partially Ready | 🟢 61-80 Ready | 🏆 81-100 Optimized

**Layers**: Agnostic (dim 1-5, max 76) + Claude-Specific (dim 6-8, max 24)

## Cleanup

If a GitHub repo was cloned to /tmp/, clean up the temp directory after analysis is complete.
