---
id: LINCE-26.3
title: Update scan skill with new detection patterns
status: To Do
assignee: []
created_date: '2026-03-06 22:52'
labels:
  - agent-ready
  - detection
milestone: m-8
dependencies:
  - LINCE-26.2
references:
  - agent-ready-skill/skills/agent-ready-scan/SKILL.md
parent_task_id: LINCE-26
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add detection patterns to agent-ready-scan/SKILL.md for all new sub-criteria:
- Batch 2: Add globs for lock files (package-lock.json, uv.lock, Cargo.lock, go.sum, poetry.lock, Pipfile.lock, Gemfile.lock, composer.lock, yarn.lock, pnpm-lock.yaml), .env.example/.env.template, .devcontainer/**/Dockerfile/docker-compose*.yml
- Batch 3: Add test file sampling for assertion quality (bare assert vs messages), type checker config detection (mypy.ini, pyrightconfig.json, tsconfig.json strict mode)
- Batch 4: Add globs for CODEOWNERS, .github/dependabot.yml, renovate.json; Grep CI workflows for security/scanning keywords
- Batch 7: Add source file sampling for type annotation presence, file size checks for >500-line files
- Phase 3 output: Update weight labels (dim 4: /12, dim 5: /10)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Batch 2 has glob patterns for all major lock file formats
- [ ] #2 Batch 2 has patterns for .env.example and devcontainer/Dockerfile
- [ ] #3 Batch 3 has assertion quality sampling logic
- [ ] #4 Batch 3 has type checker config detection
- [ ] #5 Batch 4 has CODEOWNERS, dependabot.yml, renovate.json patterns
- [ ] #6 Batch 7 has type annotation and file size checks
- [ ] #7 Phase 3 weight labels show dim 4: /12, dim 5: /10
<!-- AC:END -->
