---
id: LINCE-26
title: Deepen agent-ready assessment with new sub-criteria
status: To Do
assignee: []
created_date: '2026-03-06 22:51'
labels:
  - agent-ready
  - enhancement
milestone: m-8
dependencies: []
references:
  - agent-ready-skill/skills/agent-ready/references/scoring.md
  - agent-ready-skill/README.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add 4 new sub-criteria to 3 existing dimensions, rebalance weights (2pts dim5->dim4), update README with rationale. No new dimensions, no architecture changes.

## New Sub-criteria
- Dim 2: Environment Reproducibility (weight 25)
- Dim 3: Error Feedback Quality (weight 25)
- Dim 4: Governance Guardrails (weight 30), dim weight 10->12
- Dim 7: Code Comprehension Signals (weight 25), rename to "Documentation & Comprehension"

## Weight Changes
- Dim 4: 10 -> 12
- Dim 5: 12 -> 10
- Agnostic layer stays 76, Claude-specific stays 24, total stays 100
<!-- SECTION:DESCRIPTION:END -->
