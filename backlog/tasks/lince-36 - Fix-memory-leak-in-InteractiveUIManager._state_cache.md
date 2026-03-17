---
id: LINCE-36
title: Fix memory leak in InteractiveUIManager._state_cache
status: In Progress
assignee: []
created_date: '2026-03-16 11:19'
updated_date: '2026-03-16 18:58'
labels:
  - technical-debt
  - memory
  - optimization
dependencies: []
documentation:
  - 'backlog://workflow/overview'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The InteractiveUIManager._state_cache in interactive_ui.py grows unbounded as it accumulates all unique prompt states indefinitely.

**Issue**: 
- Each detected prompt adds ~1-5KB to the cache
- 1000 prompts = ~5MB+ leaked memory
- No cleanup mechanism exists

**Location**: `telebridge/src/telebridge/interactive_ui.py`
```python
self._state_cache[state.prompt_id] = state  # No cleanup mechanism
```

**Solution Options**:
1. Add TTL-based cleanup with timestamp tracking
2. Implement LRU eviction with max size (e.g., 100 entries)
3. Clear cache when sessions end

**Estimated Impact**: High - affects long-running sessions with many interactive prompts
<!-- SECTION:DESCRIPTION:END -->
