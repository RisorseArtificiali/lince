---
name: agent-ready-scan
description: "Full diagnostic scan of a project's agentic coding readiness. Analyzes 8 dimensions with quantitative scoring (0-100). Use when you need to evaluate how AI-ready a codebase is."
argument-hint: "[path-or-github-url]"
allowed-tools: Bash(git:*) Bash(find:*) Bash(wc:*) Bash(mkdir:*) Read Grep Glob Write
---

# Agent-Ready Scan — Full Diagnostic Analysis

Perform a comprehensive 8-dimension agentic readiness scan on the target project.

**Target**: `$ARGUMENTS` — a local path, GitHub URL, or empty for current working directory.

For the complete scoring rubric and sub-criteria definitions, see the scoring reference at `.claude/skills/agent-ready/references/scoring.md`.

## Phase 1: DISCOVER

Resolve the target directory, then execute ALL of these searches **in parallel** using simultaneous tool calls.

### Batch 1 — Agent Instructions (weight 20)
- Glob: `**/CLAUDE.md`, `**/agent.md`, `**/.cursorrules`, `**/.github/copilot-instructions.md`
- For each found file: Read it and assess quality (specific vs generic, actionable vs vague)
- Check whether instructions exist in subdirectories (not just root)

### Batch 2 — Project Navigability (weight 18)
- Glob: `**/README.md`, `**/PROJECT_INDEX.md`, `**/ARCHITECTURE.md`
- Bash: `find <target> -type d -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' -not -path '*/.venv/*' -not -path '*/venv/*' | awk -F/ '{print NF-1}' | sort -rn | head -1` to check max directory depth
- Sample 20 file names to assess naming consistency (snake_case vs camelCase vs kebab-case)

### Batch 3 — Testing & Validation (weight 16)
- Glob: `**/test*/**/*.{py,js,ts,go,rs}`, `**/*test*.{py,js,ts}`, `**/*spec*.{js,ts}`, `**/__tests__/**`
- Glob: `**/pytest.ini`, `**/jest.config*`, `**/vitest.config*`, `**/.coveragerc`, `**/pyproject.toml`
- Grep in CLAUDE.md, Makefile, package.json for test command patterns (`test`, `pytest`, `jest`, `cargo test`)

### Batch 4 — CI/CD & Automation (weight 10)
- Glob: `**/.github/workflows/*.yml`, `**/.gitlab-ci.yml`, `**/Jenkinsfile`, `**/.circleci/**`
- Glob: `**/.pre-commit-config.yaml`, `**/.husky/**`, `**/.lefthook.yml`
- Grep for linting/formatting tools in config files (ruff, eslint, prettier, black, rustfmt, gofmt)

### Batch 5 — Spec-Driven Workflow (weight 12)
- Glob: `**/specs/**`, `**/spec/**`, `**/tasks/**`, `**/prd/**`, `**/PRD/**`
- Glob: `**/docs/adr/**`, `**/adr/**`, `**/ADR/**`
- Glob: `**/.github/ISSUE_TEMPLATE/**`, `**/.github/pull_request_template*`

### Batch 6 — Skills & Tooling (weight 8)
- Glob: `**/.claude/skills/**`, `**/.claude/commands/**`
- Glob: `**/Makefile`, `**/Taskfile*`, `**/justfile`
- Glob: `**/scripts/**`, `**/tools/**`, `**/bin/**`
- Read `.claude/settings*` files for MCP configuration

### Batch 7 — Documentation (weight 8)
- Glob: `**/docs/**`, `**/CHANGELOG*`, `**/HISTORY*`
- Glob: `**/openapi*`, `**/swagger*`
- If CLAUDE.md exists, grep for links/references to other files
- Sample 3-5 source files to check docstring/comment presence

### Batch 8 — Claude-Specific (weight 8)
- Glob: `**/.claude/**`
- Glob: `**/.serena/**`
- Read `.claude/settings.local.json` if it exists
- Check for hooks configuration, MCP server setup

## Phase 2: SCORE

For each dimension, evaluate every sub-criterion on 0-100:

**Rubric**:
- **0**: Completely absent
- **25**: Minimal/placeholder (exists but not useful)
- **50**: Adequate (functional but improvable)
- **75**: Good (well-structured and useful)
- **100**: Excellent (comprehensive, contextual, well-maintained)

Calculate:
```
raw_score_d = sum(sub_score_i * sub_weight_i) / sum(sub_weight_i)    # 0-100
weighted_score_d = raw_score_d * dimension_weight_d / 100            # 0-weight
overall_score = sum(all weighted_score_d)                             # 0-100
```

## Phase 3: OUTPUT

Display results in this exact format:

```
## 🎯 Agentic Readiness Assessment

**Project**: <name>
**Overall Score**: <X>/100 <emoji> <level>

### Score Breakdown

Agent Instructions   <bar>  <weighted>/20
Project Navigability <bar>  <weighted>/18
Testing & Validation <bar>  <weighted>/16
CI/CD & Automation   <bar>  <weighted>/10
Spec-Driven Workflow <bar>  <weighted>/12
Skills & Tooling     <bar>  <weighted>/8
Documentation        <bar>  <weighted>/8
Claude-Specific      <bar>  <weighted>/8

### 🔍 Agnostic Analysis (valid for any AI agent)
Score: <X>/76

### 🤖 Claude-Specific Analysis
Score: <X>/24

### Top 3 Improvements (by impact)
1. <emoji> **<title>** (+<N> pts potential)
   <description with concrete actionable steps>
2. ...
3. ...

Run `/agent-ready fix` to auto-generate missing files.
```

**Bar format**: 16 chars wide using `█` (filled) and `░` (empty).
Fill ratio = weighted_score / dimension_weight.
Example: 14/20 = 70% → `███████████░░░░░`

After each dimension in the breakdown, add a brief 1-line finding in the conversation (what was found or missing).

## Phase 4: PERSIST

Create `claudedocs/` directory if needed, then save:

**`claudedocs/agent-ready-scores.json`** — machine-readable scores:
```json
{
  "project": "<name>",
  "timestamp": "<ISO-8601>",
  "overall_score": <0-100>,
  "level": "<Not Ready|Partially Ready|Ready|Optimized>",
  "dimensions": {
    "agent_instructions": {
      "weight": 20,
      "raw_score": <0-100>,
      "weighted_score": <0-20>,
      "subcriteria": {
        "claude_md_present": { "score": <0-100>, "weight": 25, "evidence": "<what was found>" },
        "instructions_quality": { "score": <0-100>, "weight": 25, "evidence": "<assessment>" },
        "hierarchical_instructions": { "score": <0-100>, "weight": 25, "evidence": "<what was found>" },
        "build_test_lint_refs": { "score": <0-100>, "weight": 25, "evidence": "<what was found>" }
      }
    },
    "project_navigability": { "weight": 18, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "testing_validation": { "weight": 16, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "cicd_automation": { "weight": 10, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "spec_driven_workflow": { "weight": 12, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "skills_tooling": { "weight": 8, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "documentation": { "weight": 8, "raw_score": 0, "weighted_score": 0, "subcriteria": {} },
    "claude_specific": { "weight": 8, "raw_score": 0, "weighted_score": 0, "subcriteria": {} }
  },
  "agnostic_score": { "score": 0, "max": 76 },
  "claude_specific_score": { "score": 0, "max": 24 },
  "top_improvements": [
    { "dimension": "<name>", "potential_gain": 0, "description": "<actionable steps>" }
  ]
}
```

**`claudedocs/agent-ready-report.md`** — human-readable summary (same content as conversation output plus per-dimension detailed findings).

## Important Guidelines

- Use **parallel** Glob/Grep/Read calls wherever possible — speed matters
- Be **evidence-based**: only score what you can verify through file existence and content
- Be **fair**: reward partial effort (a basic CLAUDE.md is better than none)
- Be **specific**: cite exactly what was found or missing in evidence fields
- Be **actionable**: every low score should come with a concrete fix suggestion
- If scanning a remote repo, clean up the temp clone directory after analysis
