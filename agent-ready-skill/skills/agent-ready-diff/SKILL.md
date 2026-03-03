---
name: agent-ready-diff
description: "Compare current agentic readiness state with a previous assessment. Shows score deltas per dimension, identifies improvements and regressions, and suggests next steps. Use after making changes to see progress."
argument-hint: "[path-to-previous-scores-json]"
allowed-tools: Bash(git:*) Bash(find:*) Bash(wc:*) Bash(mkdir:*) Bash(mv:*) Read Grep Glob Write
---

# Agent-Ready Diff — Delta Comparison

Compare the current project state against a previous agentic readiness assessment.

`$ARGUMENTS` may contain a path to a previous scores JSON file, otherwise use `claudedocs/agent-ready-scores.json`.

For the scoring reference, see `.claude/skills/agent-ready/references/scoring.md`.

## Step 1: Load Previous Scores

1. Read `claudedocs/agent-ready-scores.json` (or path from `$ARGUMENTS`) as the **previous** baseline
2. If not found: report that no previous assessment exists, suggest running `/agent-ready scan` first, and stop
3. Store the previous scores and timestamp

## Step 2: Archive & Rescan

1. Rename existing scores: `mv claudedocs/agent-ready-scores.json claudedocs/agent-ready-scores.prev.json`
2. Run a fresh full scan (invoke `/agent-ready-scan`) to generate **current** scores
3. Read the new `claudedocs/agent-ready-scores.json`

## Step 3: Compute Delta

For each dimension:
- `delta_weighted = current_weighted_score - previous_weighted_score`
- Direction: 📈 improved (> 0), 📉 regressed (< 0), ➡️ unchanged (= 0)

Also compute:
- Overall delta
- Agnostic layer delta
- Claude-specific layer delta

## Step 4: Display Results

```
## 📊 Agentic Readiness Delta

**Project**: <name>
**Previous**: <date> (<X>/100 <emoji>)
**Current**:  <date> (<Y>/100 <emoji>)
**Change**:   <+/-N> points <emoji>

### Dimension Changes

                     Previous  Current  Delta
Agent Instructions      14       18     +4 📈
Project Navigability    12       12      0 ➡️
Testing & Validation    14       14      0 ➡️
CI/CD & Automation       4        8     +4 📈
Spec-Driven Workflow     0        6     +6 📈
Skills & Tooling         4        4      0 ➡️
Documentation            4        6     +2 📈
Claude-Specific          0        4     +4 📈
─────────────────────────────────────────────
Overall                 52       72    +20 📈

### Layer Changes

                 Previous  Current  Delta
Agnostic (max 76)   44       48     +4 📈
Claude (max 24)      8       24    +16 📈

### 📈 Improvements
<List what improved, citing specific files added/changed that caused the score increase>

### 📉 Regressions
<List what got worse and possible reasons. If none, say "No regressions detected.">

### ➡️ Unchanged Areas
<Brief note on dimensions that didn't change>

### 🎯 Recommended Next Steps
<Top 3 actions to continue improving, ranked by impact>
```

## Step 5: Persist

- New scores already saved by the scan step
- Keep `agent-ready-scores.prev.json` for history
- The report file is also updated by the scan step

## Guidelines

- If this is the first-ever scan (no previous data), just run a normal scan and inform the user
- Be **specific** about what changed — don't just show numbers, explain what files were added/removed
- Track both improvements and regressions equally
- Suggest the highest-impact next improvement based on remaining gaps
