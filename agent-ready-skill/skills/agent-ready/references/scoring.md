# Agentic Readiness Scoring Reference

## 8 Dimensions (total weight = 100)

| # | Dimension | Weight | What it evaluates |
|---|-----------|--------|-------------------|
| 1 | Agent Instructions | 20 | CLAUDE.md, agent.md, hierarchical rules, contextual instructions |
| 2 | Project Navigability | 18 | Structure clarity, index files, README hierarchy, naming consistency, environment reproducibility |
| 3 | Testing & Validation | 16 | Test suite, coverage, documented test commands, error feedback quality |
| 4 | CI/CD & Automation | 12 | CI pipeline, linting/formatting, pre-commit hooks, governance guardrails |
| 5 | Spec-Driven Workflow | 10 | Task specs, PRD, acceptance criteria, issue templates, ADR |
| 6 | Skills & Tooling | 8 | Skills (.claude/skills/), Makefile/taskfile, support scripts, MCP config |
| 7 | Documentation & Comprehension | 8 | Linked docs, API docs, architecture docs, code comprehension signals |
| 8 | Claude-Specific | 8 | .claude/ directory, hooks, permissions, MCP server config, .serena/ |

## Layers

- **Agnostic Layer** (dimensions 1-5 generalized): max 76 points — valid for any AI coding agent
- **Claude-Specific Layer** (dimensions 6-8 + Claude details in 1-5): max 24 points

## Levels

| Emoji | Range | Level |
|-------|-------|-------|
| 🔴 | 0-30 | Not Ready |
| 🟡 | 31-60 | Partially Ready |
| 🟢 | 61-80 | Ready |
| 🏆 | 81-100 | Optimized |

## Scoring Rubric (per sub-criterion, 0-100)

- **0**: Completely absent
- **25**: Minimal/placeholder (exists but not useful)
- **50**: Adequate (functional but improvable)
- **75**: Good (well-structured and useful)
- **100**: Excellent (comprehensive, contextual, well-maintained)

## Sub-criteria Detail

### 1. Agent Instructions (weight 20)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| CLAUDE.md present in root | 25 | File exists, is non-empty |
| Instructions specific & useful | 25 | Not generic boilerplate; mentions project-specific paths, patterns, conventions |
| Hierarchical instructions in subdirs | 25 | CLAUDE.md or agent.md in key directories (src/, lib/, tests/, etc.) |
| Build/test/lint references | 25 | Explicit commands documented for building, testing, linting, formatting |

### 2. Project Navigability (weight 18)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| Logical directory structure | 20 | Max depth ≤ 4 good, ≤ 6 acceptable, > 6 penalize. Clear naming |
| Index/map file | 20 | PROJECT_INDEX.md, ARCHITECTURE.md, or equivalent |
| README in root | 20 | Overview of project, installation, usage |
| Naming consistency | 15 | Consistent case style (snake_case/camelCase), no mixed conventions |
| Environment Reproducibility | 25 | Lock files (package-lock.json, uv.lock, Cargo.lock, etc.), .env.example, devcontainer, docker-compose |

### 3. Testing & Validation (weight 16)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| Test suite present | 20 | Test files exist in tests/, __tests__/, or similar |
| Test commands documented | 20 | In CLAUDE.md, Makefile, package.json scripts, or README |
| Coverage reasonable | 20 | Coverage config present, > 60% target, or meaningful test files |
| Fast test feedback | 15 | Quick tests available (< 30s), documented how to run subset |
| Error Feedback Quality | 25 | Assertion messages present, type checking configured (mypy, pyright, tsconfig strict), helpful test failures |

### 4. CI/CD & Automation (weight 12)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| CI pipeline configured | 25 | .github/workflows/, .gitlab-ci.yml, Jenkinsfile, etc. |
| Linting/formatting automated | 25 | Ruff, eslint, prettier, rustfmt, etc. configured and runnable |
| Pre-commit hooks | 20 | .pre-commit-config.yaml, .husky/, .lefthook.yml |
| Governance Guardrails | 30 | CODEOWNERS, dependabot.yml, renovate.json, security scanning in CI |

### 5. Spec-Driven Workflow (weight 10)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| Spec/tasks directory | 30 | specs/, tasks/, prd/ directory with content |
| Issue/task templates | 30 | .github/ISSUE_TEMPLATE/, structured templates |
| ADR / decision docs | 20 | docs/adr/, decision records |
| Acceptance criteria | 20 | Defined criteria in specs/issues |

### 6. Skills & Tooling (weight 8)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| Local skills | 30 | .claude/skills/ or .claude/commands/ with content |
| Makefile/taskfile | 30 | Makefile, Taskfile.yml, justfile with useful targets |
| Support scripts | 20 | scripts/, tools/, bin/ with helpers |
| MCP config | 20 | MCP servers configured in .claude/settings* |

### 7. Documentation & Comprehension (weight 8)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| Docs linked from CLAUDE.md | 25 | CLAUDE.md references other doc files |
| API documentation | 20 | Docstrings, OpenAPI/Swagger, type annotations |
| Architecture documented | 20 | ARCHITECTURE.md, diagrams, system overview |
| Changelog/release notes | 10 | CHANGELOG.md, HISTORY.md, structured releases |
| Code Comprehension Signals | 25 | Type annotations present, file sizes reasonable (<500 lines), docstrings on key functions |

### 8. Claude-Specific (weight 8)
| Sub-criterion | Internal Weight | What to check |
|--------------|----------------|---------------|
| .claude/ directory | 30 | Directory exists with meaningful content |
| settings.local.json | 25 | Permissions configured appropriately |
| Hooks configured | 20 | Pre/post tool hooks defined |
| MCP integration | 25 | MCP servers configured (serena, context7, etc.) |

## Score Calculation

```
For each dimension d:
  raw_score_d = sum(sub_score_i * sub_weight_i) / sum(sub_weight_i)   # 0-100
  weighted_score_d = raw_score_d * dimension_weight_d / 100           # 0-weight

overall_score = sum(weighted_score_d for all d)                        # 0-100
agnostic_score = sum(weighted_score_d for d in 1..5)                   # 0-76
claude_score = sum(weighted_score_d for d in 6..8)                     # 0-24
```

## Impact Prioritization

For improvement suggestions, rank by:
```
impact = dimension_weight * (100 - raw_score) / 100
```
Higher impact = more potential points gained from fixing that dimension.

## JSON Schema for Persistence

```json
{
  "project": "string",
  "timestamp": "ISO-8601",
  "overall_score": 0-100,
  "level": "Not Ready|Partially Ready|Ready|Optimized",
  "dimensions": {
    "agent_instructions": {
      "weight": 20,
      "raw_score": 0-100,
      "weighted_score": 0-20,
      "subcriteria": {
        "claude_md_present": { "score": 0-100, "weight": 25, "evidence": "string" },
        "instructions_quality": { "score": 0-100, "weight": 25, "evidence": "string" },
        "hierarchical_instructions": { "score": 0-100, "weight": 25, "evidence": "string" },
        "build_test_lint_refs": { "score": 0-100, "weight": 25, "evidence": "string" }
      }
    },
    "project_navigability": {
      "weight": 18,
      "raw_score": 0-100,
      "weighted_score": 0-18,
      "subcriteria": {
        "logical_structure": { "score": 0-100, "weight": 20, "evidence": "string" },
        "index_file": { "score": 0-100, "weight": 20, "evidence": "string" },
        "readme_root": { "score": 0-100, "weight": 20, "evidence": "string" },
        "naming_consistency": { "score": 0-100, "weight": 15, "evidence": "string" },
        "env_reproducibility": { "score": 0-100, "weight": 25, "evidence": "string" }
      }
    },
    "testing_validation": {
      "weight": 16,
      "raw_score": 0-100,
      "weighted_score": 0-16,
      "subcriteria": {
        "test_suite": { "score": 0-100, "weight": 20, "evidence": "string" },
        "test_commands": { "score": 0-100, "weight": 20, "evidence": "string" },
        "coverage": { "score": 0-100, "weight": 20, "evidence": "string" },
        "fast_feedback": { "score": 0-100, "weight": 15, "evidence": "string" },
        "error_feedback_quality": { "score": 0-100, "weight": 25, "evidence": "string" }
      }
    },
    "cicd_automation": {
      "weight": 12,
      "raw_score": 0-100,
      "weighted_score": 0-12,
      "subcriteria": {
        "ci_pipeline": { "score": 0-100, "weight": 25, "evidence": "string" },
        "linting_formatting": { "score": 0-100, "weight": 25, "evidence": "string" },
        "pre_commit_hooks": { "score": 0-100, "weight": 20, "evidence": "string" },
        "governance_guardrails": { "score": 0-100, "weight": 30, "evidence": "string" }
      }
    },
    "spec_driven_workflow": {
      "weight": 10,
      "raw_score": 0-100,
      "weighted_score": 0-10,
      "subcriteria": {
        "spec_directory": { "score": 0-100, "weight": 30, "evidence": "string" },
        "issue_templates": { "score": 0-100, "weight": 30, "evidence": "string" },
        "adr_docs": { "score": 0-100, "weight": 20, "evidence": "string" },
        "acceptance_criteria": { "score": 0-100, "weight": 20, "evidence": "string" }
      }
    },
    "skills_tooling": {
      "weight": 8,
      "raw_score": 0-100,
      "weighted_score": 0-8,
      "subcriteria": {
        "local_skills": { "score": 0-100, "weight": 30, "evidence": "string" },
        "makefile": { "score": 0-100, "weight": 30, "evidence": "string" },
        "support_scripts": { "score": 0-100, "weight": 20, "evidence": "string" },
        "mcp_config": { "score": 0-100, "weight": 20, "evidence": "string" }
      }
    },
    "documentation_comprehension": {
      "weight": 8,
      "raw_score": 0-100,
      "weighted_score": 0-8,
      "subcriteria": {
        "docs_linked": { "score": 0-100, "weight": 25, "evidence": "string" },
        "api_docs": { "score": 0-100, "weight": 20, "evidence": "string" },
        "architecture_docs": { "score": 0-100, "weight": 20, "evidence": "string" },
        "changelog": { "score": 0-100, "weight": 10, "evidence": "string" },
        "code_comprehension_signals": { "score": 0-100, "weight": 25, "evidence": "string" }
      }
    },
    "claude_specific": {
      "weight": 8,
      "raw_score": 0-100,
      "weighted_score": 0-8,
      "subcriteria": {
        "claude_directory": { "score": 0-100, "weight": 30, "evidence": "string" },
        "settings_config": { "score": 0-100, "weight": 25, "evidence": "string" },
        "hooks_config": { "score": 0-100, "weight": 20, "evidence": "string" },
        "mcp_integration": { "score": 0-100, "weight": 25, "evidence": "string" }
      }
    }
  },
  "agnostic_score": { "score": 0, "max": 76 },
  "claude_specific_score": { "score": 0, "max": 24 },
  "top_improvements": [
    { "dimension": "string", "potential_gain": 0, "description": "string" }
  ]
}
```

## ASCII Bar Chart Format

Use `█` for filled and `░` for empty. Bar width = 16 characters.
Fill proportion = weighted_score / dimension_weight.

Example: Agent Instructions score 14/20 → 14/20 = 70% → 11 filled + 5 empty
```
Agent Instructions   ███████████░░░░░  14/20
```
