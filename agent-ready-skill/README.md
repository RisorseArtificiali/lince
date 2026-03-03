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
| 2 | Project Navigability | 18 | Structure clarity, index files, README, naming consistency |
| 3 | Testing & Validation | 16 | Test suite, documented commands, coverage, speed |
| 4 | CI/CD & Automation | 10 | Pipeline, linting, pre-commit hooks |
| 5 | Spec-Driven Workflow | 12 | Task specs, PRD, acceptance criteria, issue templates, ADR |
| 6 | Skills & Tooling | 8 | Local skills, Makefile, scripts, MCP config |
| 7 | Documentation | 8 | Linked docs, API docs, architecture, changelog |
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
CI/CD & Automation   ██████░░░░░░░░░░   4/10
Spec-Driven Workflow ░░░░░░░░░░░░░░░░   0/12
Skills & Tooling     ████████░░░░░░░░   4/8
Documentation        ████████░░░░░░░░   4/8
Claude-Specific      ░░░░░░░░░░░░░░░░   0/8
```
