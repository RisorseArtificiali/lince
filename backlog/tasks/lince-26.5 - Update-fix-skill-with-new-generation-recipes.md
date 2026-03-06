---
id: LINCE-26.5
title: Update fix skill with new generation recipes
status: To Do
assignee: []
created_date: '2026-03-06 22:52'
labels:
  - agent-ready
  - fix-recipes
milestone: m-8
dependencies:
  - LINCE-26.2
references:
  - agent-ready-skill/skills/agent-ready-fix/SKILL.md
parent_task_id: LINCE-26
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add new generation recipe sections to agent-ready-fix/SKILL.md:
- Project Navigability gaps: Generate .env.example from detected env vars, suggest adding lock files to version control
- Testing gaps: Suggest type checker config (mypy.ini/tsconfig strict) if missing, recommend assertion message patterns
- CI/CD gaps: Generate CODEOWNERS template, generate dependabot.yml/renovate.json if missing
- Documentation gaps: Note files >500 lines that should be split, suggest type annotation improvements
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 .env.example generation recipe exists
- [ ] #2 Lock file guidance exists
- [ ] #3 Type checker config templates exist
- [ ] #4 CODEOWNERS template generation exists
- [ ] #5 dependabot.yml/renovate.json generation exists
- [ ] #6 File size warning recipe exists
- [ ] #7 Type annotation suggestion recipe exists
<!-- AC:END -->
