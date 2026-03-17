---
id: LINCE-37
title: Optimize ANSI escape regex compilation in interactive_ui.py
status: To Do
assignee: []
created_date: '2026-03-16 11:19'
labels:
  - technical-debt
  - optimization
  - quick-win
dependencies: []
documentation:
  - 'backlog://workflow/overview'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The ANSI escape pattern is recompiled on every detection instead of being compiled once at module level.

**Issue**:
- `_clean_content()` called on EVERY detection
- Pattern compiled every time: `re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")`
- 1000 detections = 1000 redundant compilations (~50-100ms wasted)

**Locations**:
- `interactive_ui.py` line ~160: `InteractiveUIState.__post_init__`
- `interactive_ui.py` line ~447: `_clean_content()` method

**Solution**:
```python
# Module level
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# In _clean_content()
text = ANSI_ESCAPE.sub("", text)
```

**Estimated Impact**: Low-Medium - minor performance win, easy fix
<!-- SECTION:DESCRIPTION:END -->
