---
id: LINCE-47
title: Fix type hints and TYPE_CHECKING in bot.py to resolve linter errors
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 09:47'
labels:
  - type-safety
  - tooling
  - code-quality
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `bot.py` file has type checking issues that cause ruff to report errors for forward references to types not yet imported.

**Current Errors:**
```
telebridge/src/telebridge/bot.py:24:18: F821 Undefined name `MessageQueue`
telebridge/src/telebridge/bot.py:265:35: F821 Undefined name `InteractiveUIState`
telebridge/src/telebridge/bot.py:356:82: F821 Undefined name `MessageTask`
```

**Root Cause:**
Type hints using string quotes ("MessageQueue | None") for forward declarations, but ruff doesn't recognize them without proper TYPE_CHECKING guard.

**Fix:**
Ensure all forward type references are properly guarded:
```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telebridge.message_queue import MessageQueue
    from telebridge.interactive_ui import InteractiveUIState
    from telebridge.message_queue import MessageTask
```

**Impact:**
- Eliminates linter errors
- Better IDE support (autocompletion, type checking)
- Catches type errors during development

**Reference:**
- telebridge/src/telebridge/bot.py:24, 265, 356
<!-- SECTION:DESCRIPTION:END -->
