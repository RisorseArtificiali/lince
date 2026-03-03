---
name: agent-ready-fix
description: "Auto-generate missing files to improve a project's agentic readiness score. Creates CLAUDE.md, PROJECT_INDEX.md, Makefile, pre-commit config, spec templates, and other files based on gap analysis. Use after running agent-ready scan to fix identified gaps."
argument-hint: "[dimension-name] [path]"
disable-model-invocation: true
allowed-tools: Bash(git:*) Bash(find:*) Bash(wc:*) Bash(mkdir:*) Bash(mv:*) Read Grep Glob Write
---

# Agent-Ready Fix — Auto-Generate Missing Files

Generate missing configuration, documentation, and tooling files to improve the project's agentic readiness score.

`$ARGUMENTS` may contain a specific dimension to fix (e.g., `agent_instructions`) or be empty (fix all gaps).

For the scoring reference, see `.claude/skills/agent-ready/references/scoring.md`.

## Step 1: Load Previous Scores

1. Read `claudedocs/agent-ready-scores.json`
2. If not found, run the full scan first (invoke `/agent-ready-scan`)
3. Parse scores and identify dimensions with room for improvement

## Step 2: Prioritize

Sort dimensions by **impact** = `dimension_weight × (100 - raw_score) / 100`.

If `$ARGUMENTS` specifies a dimension name, focus only on that one.

## Step 3: Understand the Project

Before generating anything, **read existing project files** to understand:
- Language/framework (from package.json, pyproject.toml, Cargo.toml, go.mod, etc.)
- Existing build/test/lint commands (from Makefile, package.json scripts, etc.)
- Code style tools (ruff, eslint, prettier, rustfmt, etc.)
- Directory structure and naming conventions

## Step 4: Generate Files

For each gap (highest impact first), generate **contextualized** files:

### Agent Instructions gaps
- **CLAUDE.md** (root) if missing or weak:
  - Include detected language/framework
  - Include actual build/test/lint commands found in project
  - Include code style conventions from existing config
  - Reference project structure and key directories
- **Subdirectory CLAUDE.md** files for key directories (src/, lib/, tests/):
  - Contextual instructions for that part of the codebase

### Project Navigability gaps
- **PROJECT_INDEX.md**: Auto-generated map of project structure with descriptions
- **README.md** improvements: Add missing sections (only if README is absent or very sparse)

### Testing gaps
- Add test commands to CLAUDE.md if missing
- Create **Makefile** targets for test/lint if no task runner exists

### CI/CD gaps
- **`.pre-commit-config.yaml`** with language-appropriate hooks
- **`.github/workflows/ci.yml`** basic CI pipeline if missing

### Spec-Driven gaps
- **`specs/TEMPLATE.md`** with structured task template
- **`.github/ISSUE_TEMPLATE/feature.yml`** and **`bug.yml`** if missing
- **`docs/adr/0001-record-architecture-decisions.md`** ADR template

### Skills & Tooling gaps
- **Makefile** with common targets (build, test, lint, format, clean) if missing
- Basic **`.claude/skills/`** starter skill if directory is empty

### Documentation gaps
- Ensure CLAUDE.md links to key docs
- **ARCHITECTURE.md** overview if missing and project is non-trivial

### Claude-Specific gaps
- **`.claude/settings.local.json`** with sensible defaults if missing

## Step 5: Confirmation Gate

Before writing files, list ALL files that will be created and ask for user confirmation:

```
## Files to Generate

1. ✨ CLAUDE.md (root) — project instructions with build/test/lint commands
2. ✨ PROJECT_INDEX.md — project structure map
3. ✨ .pre-commit-config.yaml — Python hooks (ruff, mypy)
4. ✨ specs/TEMPLATE.md — task specification template
5. ⏭️ tests/ — already exists, skipping

Proceed? (y/n)
```

Wait for user approval before writing.

## Step 6: Validate

After generating files, re-run the scan logic to compute new scores.

## Step 7: Show Delta

```
## 🔧 Agent-Ready Fix Results

### Files Generated
- ✅ Created: CLAUDE.md (root)
- ✅ Created: PROJECT_INDEX.md
- ✅ Created: .pre-commit-config.yaml
- ✅ Created: specs/TEMPLATE.md

### Score Delta

                     Before  After  Change
Agent Instructions     14      18    +4 📈
Project Navigability   12      16    +4 📈
CI/CD & Automation      4       8    +4 📈
Spec-Driven Workflow    0       6    +6 📈
─────────────────────────────────────────
Overall               52      72    +20 📈
Level             🟡 Partial  🟢 Ready
```

## Critical Rules

- **NEVER overwrite existing files** — only create new ones or append to existing
- **Contextualize everything** — read the project first, no generic boilerplate
- **Ask before writing** — always show the file list and get confirmation
- **Respect .gitignore** — don't create files in ignored directories
- **Match conventions** — use the project's existing naming, formatting, and structure patterns
- **Real content only** — every generated file must have useful, project-specific content
