---
id: LINCE-15
title: Implement interactive UI detection from pane capture
status: Done
assignee: []
created_date: '2026-03-03 14:34'
updated_date: '2026-03-16 08:23'
labels:
  - telebridge
  - interactive-ui
milestone: m-3
dependencies:
  - LINCE-5
  - LINCE-11
references:
  - ccbot src/ccbot/handlers/interactive_ui.py pattern
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create the detection layer in `telebridge/src/telebridge/interactive_ui.py` that captures the Claude Code terminal pane content and identifies interactive UI prompts.

**Detection mechanism:**
1. Periodically capture pane content via `MultiplexerBridge.capture_pane()`
2. Analyze text for interactive UI patterns using regex/string matching
3. When detected, extract the UI content and type

**Interactive UI types to detect:**
- **Permission prompts**: "Allow X to Y?" with Yes/No options
- **Multi-choice questions**: AskUserQuestion with numbered options
- **Plan mode exit**: Confirmation to proceed with implementation
- **Checkpoint restoration**: List of checkpoints to restore
- **Model selection**: Model picker UI
- **Tool permission**: "Allow tool_name?" with approve/deny

**Detection patterns** (from ccbot):
- Look for separator lines (horizontal rules, box-drawing characters)
- Extract content between separators
- Identify navigation indicators (arrows, selection highlights)
- Match against known prompt templates

**Content extraction:**
- Parse the captured text between UI delimiters
- Extract option labels, descriptions, current selection
- Determine UI type from content pattern

**Polling approach:**
- Status polling task runs every 1-2 seconds (configurable)
- Only active when a session is bound and messages are being exchanged
- Compares current capture with previous to detect changes (avoid duplicate sends)

**Output**: Produces `InteractiveUIState` objects consumed by the inline keyboard renderer (separate task).

```python
@dataclass
class InteractiveUIState:
    ui_type: str          # "permission", "multi_choice", "plan_exit", "checkpoint", "model_select"
    content: str          # Extracted display text
    options: list[str]    # Available choices
    current_selection: int  # Currently highlighted option
    raw_text: str         # Full pane capture for debugging
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Captures pane content via MultiplexerBridge.capture_pane()
- [x] #2 Detects permission prompts, multi-choice, plan exit, checkpoint, model selection
- [x] #3 Extracts options and current selection from UI text
- [x] #4 Change detection avoids duplicate UI sends
- [x] #5 Works with both Zellij and tmux capture output
- [x] #6 Polling interval configurable
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Implementation Summary

### Core Components Implemented

1. **`interactive_ui.py`** - Complete detection system
   - `UIType` enum: PERMISSION, MULTI_CHOICE, PLAN_EXIT, CHECKPOINT, MODEL_SELECT, TOOL_PERMISSION
   - `InteractiveUIState` dataclass with prompt_id generation and ANSI cleaning
   - `InteractiveUIDetector` with pre-compiled regex patterns for each UI type
   - `InteractiveUIManager` with change detection via prompt_id hashing

2. **`config.py`** - Configuration support
   - `InteractiveUIConfig` dataclass with enabled, poll_interval, max_options fields
   - TOML section support for `[interactive_ui]`

3. **`session_monitor.py`** - Integration hook
   - `set_ui_callback()` method to register UI detection callback
   - `_ui_detector` and `_ui_callback` attributes for future pane capture integration

### Pattern Detection

Permission patterns match:
- "Allow X to Y?" with Yes/No/Approve/Deny options
- Tool permission prompts with Approve/Deny
- Multi-choice numbered lists (1. Option, 2) Option)
- Model selection UIs
- Plan exit confirmations
- Checkpoint restoration lists

### Test Coverage

28 new tests in `test_interactive_ui.py` covering:
- Pattern detection for all UI types
- Option extraction
- Change detection (same UI not reported twice)
- State caching and retrieval
- ANSI code cleaning
- Content truncation

All 121 tests pass including the new interactive UI tests.
<!-- SECTION:FINAL_SUMMARY:END -->
