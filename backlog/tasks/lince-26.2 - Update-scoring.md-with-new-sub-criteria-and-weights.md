---
id: LINCE-26.2
title: Update scoring.md with new sub-criteria and weights
status: To Do
assignee: []
created_date: '2026-03-06 22:51'
labels:
  - agent-ready
  - source-of-truth
milestone: m-8
dependencies: []
references:
  - agent-ready-skill/skills/agent-ready/references/scoring.md
parent_task_id: LINCE-26
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Primary source of truth update:
- Add Environment Reproducibility to dim 2 (weight 25), rebalance existing to 20/20/20/15
- Add Error Feedback Quality to dim 3 (weight 25), rebalance existing to 20/20/20/15
- Add Governance Guardrails to dim 4 (weight 30), rebalance to 25/25/20/30, dim weight 10->12
- Rename dim 7 to "Documentation & Comprehension", add Code Comprehension Signals (weight 25), rebalance to 25/20/20/10/25
- Update dim 5 weight 12->10
- Update JSON schema with new subcriteria keys (env_reproducibility, error_feedback_quality, governance_guardrails, code_comprehension_signals)
- Update main dimension table weights
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dim 2 has Environment Reproducibility sub-criterion (weight 25)
- [ ] #2 Dim 3 has Error Feedback Quality sub-criterion (weight 25)
- [ ] #3 Dim 4 weight is 12 with Governance Guardrails (weight 30)
- [ ] #4 Dim 5 weight is 10
- [ ] #5 Dim 7 renamed, has Code Comprehension Signals (weight 25)
- [ ] #6 JSON schema includes all 4 new subcriteria keys
- [ ] #7 All sub-weights within each dimension sum correctly
- [ ] #8 Total dimension weights sum to 100
<!-- AC:END -->
