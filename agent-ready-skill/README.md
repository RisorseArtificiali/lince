# agent-ready-skill

**Agentic Readiness Assessment** — a set of [Agent Skills](https://agentskills.io) that evaluate how well a codebase is prepared for agentic coding (AI-assisted autonomous development).

Produces a quantitative score (0-100) across 8 weighted dimensions plus actionable guidance to improve readiness.

## Skills

| Skill | Command | Description |
|-------|---------|-------------|
| **agent-ready** | `/agent-ready` | Main entry point — routes to sub-commands, defaults to scan |
| **agent-ready-scan** | `/agent-ready-scan` | Full diagnostic analysis across 8 dimensions |
| **agent-ready-fix** | `/agent-ready-fix` | Auto-generate missing files to improve score |
| **agent-ready-report** | `/agent-ready-report` | Detailed report in `claudedocs/` with roadmap |
| **agent-ready-diff** | `/agent-ready-diff` | Delta comparison with previous assessment |

## Scoring Dimensions

| # | Dimension | Weight | What it evaluates |
|---|-----------|--------|-------------------|
| 1 | Agent Instructions | 20 | CLAUDE.md, hierarchical rules, build/test/lint docs |
| 2 | Project Navigability | 18 | Structure, index files, README, naming, environment reproducibility |
| 3 | Testing & Validation | 16 | Test suite, documented commands, coverage, error feedback |
| 4 | CI/CD & Automation | 12 | Pipeline, linting, pre-commit hooks, governance |
| 5 | Spec-Driven Workflow | 10 | Task specs, PRD, acceptance criteria, issue templates, ADR |
| 6 | Skills & Tooling | 8 | Local skills, Makefile, scripts, MCP config |
| 7 | Documentation & Comprehension | 8 | Linked docs, API docs, architecture, code signals |
| 8 | Claude-Specific | 8 | .claude/ directory, settings, hooks, MCP integration |

**Two analysis layers**:
- **Agnostic** (dimensions 1-5, max 76 pts) — valid for any AI coding agent
- **Claude-Specific** (dimensions 6-8, max 24 pts) — specific to Claude Code

**Score levels**: 🔴 0-30 Not Ready | 🟡 31-60 Partially Ready | 🟢 61-80 Ready | 🏆 81-100 Optimized

## Usage

```
/agent-ready                              # scan current project (default)
/agent-ready scan                         # same as above
/agent-ready scan https://github.com/o/r  # scan a GitHub repo
/agent-ready fix                          # generate missing files
/agent-ready report                       # detailed report in claudedocs/
/agent-ready diff                         # compare with previous scan
```

## Installation

The skills follow the [Agent Skills](https://agentskills.io) open standard. They live in `skills/` and are symlinked into `.claude/skills/` for Claude Code discovery.

For a fresh clone, recreate the symlinks:

```bash
cd /path/to/lince
for skill in agent-ready agent-ready-scan agent-ready-fix agent-ready-report agent-ready-diff; do
  ln -sf "$(pwd)/agent-ready-skill/skills/$skill" ".claude/skills/$skill"
done
```

## Directory Structure

```
agent-ready-skill/
├── README.md
└── skills/
    ├── agent-ready/              # Main router skill
    │   ├── SKILL.md
    │   └── references/
    │       └── scoring.md        # Shared scoring rubric & JSON schema
    ├── agent-ready-scan/         # Full diagnostic scan
    │   └── SKILL.md
    ├── agent-ready-fix/          # Auto-generate missing files
    │   └── SKILL.md
    ├── agent-ready-report/       # Detailed report generation
    │   └── SKILL.md
    └── agent-ready-diff/         # Delta comparison
        └── SKILL.md
```

## Compatibility

These skills are designed for [Claude Code](https://claude.ai/code) but follow the open Agent Skills format. The scoring dimensions and analysis are agent-agnostic — only dimensions 6-8 are Claude-specific.

## Output Example

```
## 🎯 Agentic Readiness Assessment

Project: my-project
Overall Score: 52/100 🟡 Partially Ready

Score Breakdown

Agent Instructions   ███████████░░░░░  14/20
Project Navigability ██████████░░░░░░  12/18
Testing & Validation ██████████████░░  14/16
CI/CD & Automation   ██████░░░░░░░░░░   4/12
Spec-Driven Workflow ░░░░░░░░░░░░░░░░   0/10
Skills & Tooling     ████████░░░░░░░░   4/8
Documentation        ████████░░░░░░░░   4/8
Claude-Specific      ░░░░░░░░░░░░░░░░   0/8
```

## Why These Dimensions?

The 8 dimensions are chosen based on what actually impacts agentic coding effectiveness. Each dimension reflects a real friction point that AI agents encounter when working autonomously.

### 1. Agent Instructions (weight 20) — Foundation
**Why it matters**: Without explicit instructions, agents operate blindly. A well-crafted CLAUDE.md is the difference between an agent that makes 100 wrong assumptions and one that understands project-specific patterns from the start. The 20-point weight reflects that this is the single highest-leverage improvement for agent effectiveness.

**Agent impact**: Reduces context-gathering loops, prevents boilerplate mistakes, accelerates initial exploration.

### 2. Project Navigability (weight 18) — Orientation
**Why it matters**: Agents need to orient themselves quickly. Deep directory structures, inconsistent naming, and missing index files force agents to exhaustively explore the codebase before taking action. Environment reproducibility (lock files, container configs) ensures agents can actually run the code they analyze.

**Agent impact**: Faster orientation, fewer traversal steps, reproducible analysis environments.

### 3. Testing & Validation (weight 16) — Confidence
**Why it matters**: Tests are the agent's safety net. Well-documented test commands and fast feedback loops enable agents to verify changes without breaking production. Error feedback quality (assertion messages, type checking) transforms cryptic failures into actionable diagnostics that agents can understand and fix.

**Agent impact**: Safer autonomous changes, faster iteration, interpretable failure modes.

### 4. CI/CD & Automation (weight 12) — Quality Gates
**Why it matters**: CI pipelines and pre-commit hooks encode project quality standards that agents must respect. Governance guardrails (CODEOWNERS, dependency updates, security scanning) prevent agents from introducing vulnerabilities or bypassing review processes.

**Agent impact**: Aligns agent output with project quality standards, prevents bypassing safety checks.

### 5. Spec-Driven Workflow (weight 10) — Intent Alignment
**Why it matters**: Specs, ADRs, and issue templates document intent. Agents that understand the "why" behind requirements produce better implementations than those blindly following instructions. Acceptance criteria provide unambiguous completion signals.

**Agent impact**: Better alignment with user intent, fewer requirement mismatches, verifiable completion.

### 6. Skills & Tooling (weight 8) — Force Multipliers
**Why it matters**: Local skills and MCP servers extend agent capabilities. A well-configured Makefile provides runnable commands that agents can discover and execute. These tools multiply what agents can accomplish autonomously.

**Agent impact**: Extended capabilities, discoverable automation, reduced manual steps.

### 7. Documentation & Comprehension (weight 8) — Semantic Understanding
**Why it matters**: Documentation links and API docs connect code to concepts. Code comprehension signals (type annotations, reasonable file sizes, docstrings) make codebases semantically transparent to agents. A 500-line file with no types is a black box; a 200-line typed file with docstrings is readable.

**Agent impact**: Better semantic understanding, reduced codebase opacity, fewer blind experiments.

### 8. Claude-Specific (weight 8) — Platform Integration
**Why it matters**: Claude Code has unique capabilities (hooks, permissions, MCP integration) that require configuration. This dimension measures how well the project leverages Claude-specific features.

**Agent impact**: Enables Claude-specific workflows, proper tool permissions, MCP-powered capabilities.

## Layer Rationale

### Agnostic Layer (dimensions 1-5, max 76 pts)
These dimensions are universal for any AI coding agent—Claude, GitHub Copilot, Tabnine, or future agents. Investing here yields benefits regardless of which agent you use.

### Claude-Specific Layer (dimensions 6-8, max 24 pts)
These dimensions capture Claude Code's unique capabilities. Investing here improves results specifically for Claude users but doesn't transfer to other agents.

The 76:24 split reflects that most agentic readiness improvements are universal, with ~24% being platform-specific optimizations.
